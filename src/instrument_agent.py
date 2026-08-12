"""Measure how often an agent silently fails, and how much of the clock budget it uses.

Two of the three confirmed ladder gains in this project were crash/veto fixes, not strategy
changes: the `random.sample` clip and the `detect_matchup` `None` guard. Both were exceptions the
agent caught and turned into a degraded-but-legal move, so nothing in the win rate or the frozen
panel pointed at them — they were found by reading code. This module measures that failure class
directly instead.

The measurement that matters is *swallowed* exceptions. An exception that escapes `agent()` is
trivially observable (the battle crashes). An exception the agent catches — `except Exception:
score = -999999` inside a per-option scoring loop, say — leaves a legal selection behind and is
invisible from the outside, even though every option being floored turns the decision into a
coin flip. `sys.monitoring` (Python 3.12+) reports RAISE events regardless of whether the
exception is later handled, which is exactly the hook this needs, and it costs nothing on the
non-raising path because CPython only arms the instrumented code objects.

Scoped to the candidate's own directory: an exception raised inside `cg` or the stdlib is the
engine's business, and counting it would bury the agent's own failures in noise.

Usage:
    python3 src/instrument_agent.py --candidate submissions/masamikobayashi_archaludon_cinderace \
        --battles 600 --workers 8
"""

# MUST run before anything imports numpy — see the same block in `ladder_eval.py` for the
# measurement behind this (unpinned BLAS cost 24.3 s CPU per battle and made 8 workers slower
# than serial). `il_agent_v2b` and friends pull a threaded BLAS in through their scorer.
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import Counter as _Counter  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ladder_eval  # noqa: E402
from ladder_eval import DEFAULT_PANEL  # noqa: E402

# sys.monitoring tool ids 0-5 are reserved for specific profilers; 5 is the free-for-all slot.
_TOOL_ID = 5

# Exceptions that are ordinary control flow, not failures. Every `any(...)`/`sum(...)` over a
# generator ends by raising StopIteration, so counting these turns the whole measurement into a
# genexp census: the first run of this module reported a 39% "swallowed" rate whose top three
# sites were all plain generator expressions.
_BENIGN = (StopIteration, StopAsyncIteration, GeneratorExit)


class Counters:
    """Per-process tallies. Merged in the parent — never shared across processes."""

    def __init__(self):
        self.decisions = 0
        self.escaped = 0          # exception left agent() entirely; we substituted a fallback
        self.swallowed = 0        # exception raised inside agent code and handled internally
        self.raise_sites = _Counter()   # (filename, lineno) -> count
        self.latencies_ms = []
        self.battles = 0
        self.battle_seconds = []

    def merge(self, other: "Counters") -> "Counters":
        self.decisions += other.decisions
        self.escaped += other.escaped
        self.swallowed += other.swallowed
        self.raise_sites.update(other.raise_sites)
        self.latencies_ms.extend(other.latencies_ms)
        self.battles += other.battles
        self.battle_seconds.extend(other.battle_seconds)
        return self

    def to_dict(self, top_sites: int = 12) -> dict:
        return {
            "battles": self.battles,
            "decisions": self.decisions,
            "escaped": self.escaped,
            "escaped_rate": self.escaped / self.decisions if self.decisions else 0.0,
            "swallowed": self.swallowed,
            "swallowed_rate": self.swallowed / self.decisions if self.decisions else 0.0,
            "battles_with_any_swallow": self.battles_with_swallow,
            "decision_ms_p50": percentile(self.latencies_ms, 50),
            "decision_ms_p99": percentile(self.latencies_ms, 99),
            "decision_ms_max": percentile(self.latencies_ms, 100),
            "battle_seconds_p50": percentile(self.battle_seconds, 50),
            "battle_seconds_max": percentile(self.battle_seconds, 100),
            "top_raise_sites": [
                {"site": f"{f}:{ln}", "count": c}
                for (f, ln), c in self.raise_sites.most_common(top_sites)
            ],
        }

    # set by the worker; kept off __init__ so merge() stays a plain sum
    battles_with_swallow = 0


def percentile(values, pct: float) -> float:
    """Nearest-rank percentile: the smallest value at or above which `pct`% of the sample lies.

    `ceil`, not `round` — the nearest-rank definition is ceil(p/100 * n), and Python's `round` is
    banker's rounding, which sends p50 of a 5-element sample to index 1 instead of the middle.
    Derived here rather than pulled from numpy: this module runs in the same pinned-BLAS context
    as `ladder_eval` and has no reason to import numpy at all.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 100:
        return ordered[-1]
    rank = max(1, min(len(ordered), math.ceil(pct / 100.0 * len(ordered))))
    return ordered[rank - 1]


def legal_fallback(obs_dict: dict):
    """The most conservative selection the engine will accept for this observation.

    Returns None for the deck-selection phase (`select is None`) — the caller must supply the
    deck there, and inventing 60 card IDs here would silently change which deck was measured.
    """
    sel = obs_dict.get("select")
    if sel is None:
        return None
    n = len(sel.get("option") or [])
    min_c = int(sel.get("minCount") or 0)
    max_c = int(sel.get("maxCount") or 0)
    if n == 0 or max_c == 0:
        return []
    k = min_c if min_c > 0 else min(1, max_c)
    k = min(k, max_c, n)
    return list(range(k))


class _RaiseWatcher:
    """Counts RAISE events originating in files under `roots`, while active.

    Uses `sys.monitoring` so handled exceptions are counted too. `sys.settrace` would also see
    them but slows every Python line in the process by an order of magnitude, which would corrupt
    the latency numbers this same run is trying to measure.
    """

    def __init__(self, roots, counters: Counters):
        self.roots = [str(Path(r).resolve()) for r in roots]
        self.counters = counters
        self.hits = 0
        self._armed = False
        self._scope_cache: dict = {}
        self._line_cache: dict = {}

    def _in_scope(self, filename: str) -> bool:
        hit = self._scope_cache.get(filename)
        if hit is None:
            hit = any(filename.startswith(root) for root in self.roots)
            self._scope_cache[filename] = hit
        return hit

    def _lineno(self, code, instruction_offset: int) -> int:
        """Resolve the bytecode offset to the source line that actually raised.

        `co_firstlineno` would name the enclosing function, which is no use for diagnosis — a
        1,100-line agent has a handful of functions and dozens of distinct raise sites. The
        per-code offset map is built once and cached; `dis` is stdlib and only runs on first sight
        of each code object, so it stays off the hot path.
        """
        table = self._line_cache.get(code)
        if table is None:
            import dis

            table = {i.offset: (i.positions.lineno if i.positions else None)
                     for i in dis.get_instructions(code)}
            self._line_cache[code] = table
        return table.get(instruction_offset) or code.co_firstlineno

    def _on_raise(self, code, instruction_offset, exception):
        if isinstance(exception, _BENIGN):
            return
        filename = code.co_filename
        if not self._in_scope(filename):
            return
        self.hits += 1
        self.counters.swallowed += 1
        self.counters.raise_sites[(filename, self._lineno(code, instruction_offset))] += 1

    def arm(self):
        mon = sys.monitoring
        try:
            mon.use_tool_id(_TOOL_ID, "instrument_agent")
        except ValueError:
            pass  # already claimed by this process on an earlier arm()
        mon.register_callback(_TOOL_ID, mon.events.RAISE, self._on_raise)
        mon.set_events(_TOOL_ID, mon.events.RAISE)
        self._armed = True

    def disarm(self):
        if not self._armed:
            return
        mon = sys.monitoring
        mon.set_events(_TOOL_ID, 0)
        mon.register_callback(_TOOL_ID, mon.events.RAISE, None)
        try:
            mon.free_tool_id(_TOOL_ID)
        except ValueError:
            pass
        self._armed = False


def _agent_source_root(agent_fn) -> str:
    """Directory holding the agent's own source, used to scope RAISE events to its code.

    For a real candidate this is `submissions/<name>/`, since `_load_agent_isolated` hands back
    `main.py`'s `agent`. Falls back to the repo root if the callable has no code object (a C
    builtin, say), which over-counts rather than silently under-counting.
    """
    code = getattr(agent_fn, "__code__", None)
    if code is None:
        return str(REPO_ROOT)
    return str(Path(code.co_filename).resolve().parent)


def wrap_agent(agent_fn, counters: Counters, watcher: "_RaiseWatcher | None" = None):
    """Wrap `agent_fn` so every decision is timed and every failure is counted.

    An escaping exception is replaced with `legal_fallback` so one bad decision does not abort the
    battle and cost us the rest of the sample. That substitution is itself counted — a run with a
    non-zero `escaped` is measuring a partly-substituted policy, not the agent's own.

    When no `watcher` is supplied one is created and armed here, scoped to the agent's own source
    directory. The battle harness passes an explicit watcher instead, so it can arm once per chunk
    rather than once per wrap and can also attribute raises to individual battles.

    Attribution note: an exception that escapes also fires a RAISE event, so the escaping raise is
    deducted from `swallowed`. `swallowed` therefore means "raised inside the agent's own code and
    handled there", which is the number worth acting on.
    """
    owns_watcher = watcher is None
    if owns_watcher:
        watcher = _RaiseWatcher([_agent_source_root(agent_fn)], counters)
        watcher.arm()

    def wrapped(obs_dict):
        counters.decisions += 1
        before = watcher.hits
        t0 = time.perf_counter()
        try:
            out = agent_fn(obs_dict)
        except Exception:
            counters.escaped += 1
            if watcher.hits > before:
                counters.swallowed -= 1  # that raise escaped; it was not swallowed
            out = legal_fallback(obs_dict)
        finally:
            counters.latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if watcher.hits > before:
            wrapped.raised_this_battle = True
        return out

    wrapped.raised_this_battle = False
    wrapped.watcher = watcher
    return wrapped


# ---------------------------------------------------------------------------
# worker side — processes, not threads: the cg engine is a ctypes singleton with a
# process-global Battle.battle_ptr.
# ---------------------------------------------------------------------------

_CAND: dict = {}


def _worker_init(engine_dir: str, candidate_dir: str):
    """Delegate to `ladder_eval`'s worker init rather than re-implementing it.

    It sets up the engine handles, the `run_battle` helper module, and the per-worker agent cache
    that `_get` and `_load_agent_isolated` both read out of `ladder_eval._W`. An earlier version of
    this file kept its own state dict and called `_load_agent_isolated` anyway, which raised
    `KeyError: 'rb'` in every worker — and because a Pool respawns failed workers, that produced an
    unbounded traceback loop instead of a clean exit.
    """
    ladder_eval._worker_init(engine_dir)
    _CAND["dir"] = candidate_dir


def _run_chunk(task):
    opponent_dir, n_battles, offset = task
    counters = Counters()
    cand_dir = _CAND["dir"]

    cand_agent, cand_deck = ladder_eval._get(cand_dir)
    opp_agent, opp_deck = ladder_eval._get(opponent_dir)

    watcher = _RaiseWatcher([cand_dir], counters)
    wrapped = wrap_agent(cand_agent, counters, watcher)

    battle_start = ladder_eval._W["start"]
    battle_select = ladder_eval._W["select"]
    battle_finish = ladder_eval._W["finish"]

    watcher.arm()
    battles_with_swallow = 0
    try:
        for i in range(n_battles):
            cand_first = (offset + i) % 2 == 0
            decks = (cand_deck, opp_deck) if cand_first else (opp_deck, cand_deck)
            agents = (wrapped, opp_agent) if cand_first else (opp_agent, wrapped)

            obs, _start = battle_start(decks[0], decks[1])
            if obs is None:
                continue
            before = watcher.hits
            t0 = time.perf_counter()
            while obs["current"]["result"] == -1:
                slot = obs["current"]["yourIndex"]
                obs = battle_select(agents[slot](obs))
            counters.battle_seconds.append(time.perf_counter() - t0)
            counters.battles += 1
            if watcher.hits > before:
                battles_with_swallow += 1
            battle_finish()
    finally:
        watcher.disarm()

    counters.battles_with_swallow = battles_with_swallow
    return counters


def instrument(candidate_dir: Path, battles: int, workers: int, opponents) -> dict:
    engine_dir = REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission"
    opponent_dirs = [str(Path(o).resolve()) for o in opponents]
    per_opponent = max(1, battles // len(opponent_dirs))

    chunk = max(1, per_opponent // max(1, workers))
    tasks = []
    for d in opponent_dirs:
        done = 0
        while done < per_opponent:
            n = min(chunk, per_opponent - done)
            tasks.append((d, n, done))
            done += n

    total = Counters()
    with Pool(
        processes=workers,
        initializer=_worker_init,
        initargs=(str(engine_dir), str(Path(candidate_dir).resolve())),
    ) as pool:
        swallow_battles = 0
        for c in pool.imap_unordered(_run_chunk, tasks):
            swallow_battles += c.battles_with_swallow
            total.merge(c)
    total.battles_with_swallow = swallow_battles
    return total.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--battles", type=int, default=600)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--opponents",
        nargs="*",
        default=None,
        help="Defaults to the frozen panel minus the candidate itself.",
    )
    parser.add_argument("--json", help="Write the report to this path as well as stdout.")
    args = parser.parse_args()

    candidate = Path(args.candidate).resolve()
    opponents = args.opponents or [
        str(p) for p in DEFAULT_PANEL if Path(p).resolve() != candidate
    ]

    report = instrument(candidate, args.battles, args.workers, opponents)
    report["candidate"] = str(candidate.relative_to(REPO_ROOT)) if candidate.is_relative_to(REPO_ROOT) else str(candidate)
    print(json.dumps(report, indent=2))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
