"""Frozen-panel TrueSkill evaluation — the primary local ranking gate.

Replaces `src/local_eval.py`'s pooled win rate for *ranking* candidates. `local_eval.py` stays
useful for a quick single-candidate smoke test; this module is what a submission decision should
be based on.

Two defects in the pooled-win-rate approach that this fixes:

1. `local_eval.py:136` drops the candidate from its own opponent roster, so roster members face a
   strictly easier field than non-members. Measured: Archaludon (a roster member) holds
   `il_agent_v2b` to 7.3%, Dragapult to 19.3%, aristophanivan to 30.7% — and never plays that
   matchup when it is itself the candidate. Here, panel ratings are fit once and FROZEN, and the
   candidate is scored against fixed opponent ratings, so the estimate is not distorted by which
   subset of the panel it happened to face.

2. 30 battles x 7 opponents = 210 games gives a Wilson half-width of +/-6.6pp, far too wide to
   separate candidates 3pp apart. The engine does ~38 battles/sec/core on 10 cores, so 4,000
   games/matchup (+/-1.5pp) costs seconds. There was never a compute constraint.

Honest limitation, measured in `test_trueskill_lite.py`: under the strong intransitivity this
field actually exhibits (Archaludon beats Dragapult 80.7% but loses to Crustle 32.7%, while
Crustle's real ladder score is far below Dragapult's), frozen-panel mu is *qualitatively* better
behaved than pooled WR — it does not drop mechanically when a hard opponent joins the field — but
its residual distortion is not automatically smaller in magnitude. Both numbers are reported.
The decisive evidence is the calibration set in `src/calibration_tracker.py`, not the theory.

There is no seed control: `cg/libcg.so` exports no seeding entry point and links
std::random_device, so battles cannot be replayed and Common Random Numbers is impossible.
Variance is handled with sample size and with blocking on the opponent panel instead.

Usage:
    # Fit and freeze the reference panel (do this once; re-run only when the panel changes)
    python3 src/ladder_eval.py fit-panel --games 2000

    # Rate a candidate against the frozen panel
    python3 src/ladder_eval.py rate --candidate submissions/kiyota_dragapult_ex --games 4000

    # Blocked head-to-head: both rated on the identical field (panel minus both)
    python3 src/ladder_eval.py compare --a submissions/A --b submissions/B --games 4000

    # Roster-overfitting check: rate on 5 seen panel members, report 2 held out separately
    python3 src/ladder_eval.py rate --candidate submissions/X --holdout 2

    # Harvest the candidate's own trajectory states, for adversarial validation
    python3 src/ladder_eval.py rate --candidate submissions/il_agent_v2b --dump-states data/processed/selfplay
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

# MUST run before anything imports numpy — BLAS reads these once, at library load.
#
# `il_agent_v2b` is the sklearn/numpy variant of the IL agent (the pure-Python `pure_predictor`
# rewrite is a different submission), so having it on the panel pulls a threaded BLAS into every
# worker. Measured: one battle against it cost 0.45 s wall and 24.3 s CPU across ~6.5 threads.
# Pinned to one thread the *same* battle costs 0.075 s wall and 0.075 s CPU — 54x less CPU and
# 6x less wall clock, because the BLAS pool was thrashing on matrices far too small to parallelise.
# With N worker processes each spawning its own BLAS pool this compounds: an 8-worker panel fit
# burned 343 s of system time and ran 2.8x *slower* than serial.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_BATTLE_SCRIPT = REPO_ROOT / ".claude" / "skills" / "run-battle" / "scripts" / "run_battle.py"
PANEL_RATINGS_PATH = REPO_ROOT / "data" / "processed" / "panel_ratings.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trueskill_lite import (  # noqa: E402
    Rating,
    rate_1vs1,
    rate_against_fixed,
    DEFAULT_MU,
    DEFAULT_SIGMA,
    DEFAULT_BETA,
)
from local_eval import wilson_interval  # noqa: E402

DEFAULT_PANEL = [
    REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission",
    REPO_ROOT / "submissions" / "kiyota_mega_lucario_ex",
    REPO_ROOT / "submissions" / "masamikobayashi_archaludon_cinderace",
    REPO_ROOT / "submissions" / "soutasakurai_libraryout_crustle",
    REPO_ROOT / "submissions" / "il_agent_v2b",
    REPO_ROOT / "submissions" / "aristophanivan_probablity_v2",
    REPO_ROOT / "submissions" / "biohack44_alakazam_dunsparce",
]

# Repeated passes over the same round-robin during panel fitting would drive sigma to ~0 and make
# the frozen panel absurdly overconfident. Floor it at a value reflecting genuine residual
# uncertainty about a fixed agent's strength.
PANEL_SIGMA_FLOOR = 25.0


# ---------------------------------------------------------------------------
# worker side (one process per core; the cg engine is a ctypes singleton with a
# process-global Battle.battle_ptr, so workers MUST be processes, not threads)
# ---------------------------------------------------------------------------

_W: dict = {}


def _load_run_battle_module():
    spec = importlib.util.spec_from_file_location("run_battle", RUN_BATTLE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_battle"] = module
    spec.loader.exec_module(module)
    return module


def _worker_init(engine_dir: str):
    sys.path.insert(0, engine_dir)
    from cg.game import battle_start, battle_select, battle_finish

    _W["start"] = battle_start
    _W["select"] = battle_select
    _W["finish"] = battle_finish
    _W["rb"] = _load_run_battle_module()
    _W["agents"] = {}
    _W["decks"] = {}


def _load_agent_isolated(agent_dir: Path, module_name: str):
    """Load one agent's `main.py` without letting its helper modules leak into the next agent's.

    Submissions are independent bundles that happen to share helper filenames: `il_agent_v1`,
    `il_agent_v2`, `il_agent_v2b` and `il_agent_v3` each ship their own `il_features.py`. Each
    `main.py` does `sys.path.insert(0, <its own dir>)` then `import il_features`, so in a
    long-lived process the *first* agent to load wins `sys.modules["il_features"]` and every later
    agent silently gets someone else's helper. Kaggle never sees this — one agent per process —
    but this harness loads seven of them into one worker.

    That is not a hypothetical: rating `il_agent_v2` against a panel containing `il_agent_v2b`
    crashed with `AttributeError: module 'il_features' has no attribute 'load_card_attrs'`,
    because v2's older helper shadowed v2b's. The crash was the lucky case — when the shadowing
    helper happens to expose the same names, the agent runs to completion on the wrong feature
    code and the resulting rating is quietly wrong.

    So: snapshot `sys.path` and `sys.modules` around the exec, then restore the path and evict any
    module that was newly imported *from inside this agent's directory*. Shared third-party
    modules (numpy, joblib) are left cached — they are genuinely shared, and re-importing them per
    agent would be expensive for no benefit. Already-executed agents keep working because their
    module globals hold direct references to their own helper objects; only the name-to-module
    cache entry is dropped.
    """
    agent_root = agent_dir.resolve()
    saved_path = list(sys.path)
    before = set(sys.modules)
    try:
        return _W["rb"].load_agent(agent_dir / "main.py", module_name)
    finally:
        sys.path[:] = saved_path
        for name in set(sys.modules) - before:
            if name == module_name:
                continue
            mod = sys.modules.get(name)
            origin = getattr(mod, "__file__", None)
            if not origin:
                continue
            try:
                Path(origin).resolve().relative_to(agent_root)
            except ValueError:
                continue  # not from this agent's bundle — genuinely shared, keep it cached
            del sys.modules[name]


def _get(agent_dir: str):
    if agent_dir not in _W["agents"]:
        d = Path(agent_dir)
        # Stable module name: `hash()` of a str is salted per process, so it would give the same
        # agent a different module name in every worker and in every run.
        module_name = "agent_" + hashlib.sha256(agent_dir.encode()).hexdigest()[:12]
        _W["agents"][agent_dir] = _load_agent_isolated(d, module_name)
        _W["decks"][agent_dir] = _W["rb"].load_deck(d)
    return _W["agents"][agent_dir], _W["decks"][agent_dir]


def _run_chunk(task):
    """Play a chunk of battles between two agents.

    task = (a_dir, b_dir, n_battles, offset, dump_dir_or_None, dump_side)
    Returns (a_dir, b_dir, wins_for_a: list[bool], errors: int).

    `offset` continues the alternating first-player pattern across chunks so the split into
    chunks never biases who moves first.
    """
    a_dir, b_dir, n, offset, dump_dir, dump_side = task
    agent_a, deck_a_cards = _get(a_dir)
    agent_b, deck_b_cards = _get(b_dir)

    wins, errors = [], 0
    dumped = []
    for i in range(n):
        a_first = (offset + i) % 2 == 0
        decks = (deck_a_cards, deck_b_cards) if a_first else (deck_b_cards, deck_a_cards)
        agents = (agent_a, agent_b) if a_first else (agent_b, agent_a)

        obs, _start = _W["start"](decks[0], decks[1])
        if obs is None:
            errors += 1
            continue

        # index of the agent whose states we harvest, in slot terms
        dump_slot = None
        if dump_dir is not None:
            dump_slot = 0 if (a_first == (dump_side == "a")) else 1
        # Must be unique across the whole dump, not just within this chunk: a worker plays chunks
        # against several opponents and `offset` restarts at 0 for each, so pid+offset alone
        # collides. Colliding ids would merge distinct episodes into one GroupKFold group and let
        # adversarial validation leak across its own folds.
        episode_id = f"selfplay_{os.getpid()}_{Path(b_dir).name}_{offset + i}"
        pending = []

        while obs["current"]["result"] == -1:
            slot = obs["current"]["yourIndex"]
            select_list = agents[slot](obs)
            if dump_slot is not None and slot == dump_slot and obs.get("select") is not None:
                pending.append(
                    {
                        "episode_id": episode_id,
                        "select": obs["select"],
                        "current": obs["current"],
                        "action": list(select_list),
                    }
                )
            obs = _W["select"](select_list)

        winner_slot = obs["current"]["result"]
        a_won = (winner_slot == 0) == a_first
        wins.append(a_won)

        if pending:
            dumper_won = (winner_slot == dump_slot)
            for rec in pending:
                rec["actor_reward"] = 1 if dumper_won else 0
                rec["actor_score"] = None
                rec["opp_score"] = None
            dumped.extend(pending)
        _W["finish"]()

    if dumped:
        shard = Path(dump_dir) / f"shard_{os.getpid()}.jsonl"
        with shard.open("a") as f:
            for rec in dumped:
                f.write(json.dumps(rec) + "\n")

    return a_dir, b_dir, wins, errors


# ---------------------------------------------------------------------------
# driver side
# ---------------------------------------------------------------------------


def _chunk_tasks(a_dir, b_dir, games, workers, dump_dir=None, dump_side=None):
    per = max(1, games // workers)
    tasks, done = [], 0
    while done < games:
        n = min(per, games - done)
        tasks.append((str(a_dir), str(b_dir), n, done, dump_dir, dump_side))
        done += n
    return tasks


def _run_all(tasks, engine_dir, workers, progress: bool = True):
    """Run tasks across a process pool, returning {(a,b): [wins_for_a...], ...} and error counts.

    Uses `imap_unordered` rather than `map` so a slow chunk cannot stall the whole batch behind it
    and so progress is observable — battle cost varies ~25x across the panel (`il_agent_v2b` runs
    a pure-Python decision-tree scorer at ~0.8 s/battle against ~0.03 s for the rule-based agents),
    which makes a silent `map` look indistinguishable from a hang.
    """
    results, errors = {}, {}
    total_battles = sum(t[2] for t in tasks)
    done_battles = 0
    if workers == 1:
        _worker_init(str(engine_dir))
        outs = [_run_chunk(t) for t in tasks]
    else:
        outs = []
        with Pool(workers, initializer=_worker_init, initargs=(str(engine_dir),)) as pool:
            for out in pool.imap_unordered(_run_chunk, tasks):
                outs.append(out)
                done_battles += len(out[2]) + out[3]
                if progress:
                    print(f"\r  {done_battles}/{total_battles} battles "
                          f"({done_battles / total_battles * 100:.0f}%)", end="", flush=True)
        if progress:
            print()
    for a, b, wins, errs in outs:
        results.setdefault((a, b), []).extend(wins)
        errors[(a, b)] = errors.get((a, b), 0) + errs
    return results, errors


def _interleave(per_opponent: dict) -> list:
    """Flatten {opponent: [(rating, won), ...]} round-robin so sigma shrinks evenly across the
    field rather than converging against whichever opponent happened to be processed first."""
    lists = [v for v in per_opponent.values() if v]
    if not lists:
        return []
    out = []
    for i in range(max(len(x) for x in lists)):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
    return out


def panel_version(panel: list, games: int) -> str:
    payload = json.dumps(
        {"panel": sorted(Path(p).name for p in panel), "games_per_pair": games,
         "mu": DEFAULT_MU, "sigma": DEFAULT_SIGMA, "beta": DEFAULT_BETA,
         "sigma_floor": PANEL_SIGMA_FLOOR},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def fit_panel(panel: list, games: int, workers: int, max_passes: int = 200, tol: float = 0.01):
    """Round-robin every panel pair, then fit ratings by iterating the online TrueSkill update to
    convergence. tau=0 during fitting (no drift — these are fixed agents, and the whole point is
    a stable reference frame)."""
    rb = _load_run_battle_module()
    engine_dir = rb.find_engine_dir(*panel)

    tasks = []
    for i, a in enumerate(panel):
        for b in panel[i + 1:]:
            tasks.extend(_chunk_tasks(a, b, games, workers))
    print(f"fitting panel: {len(panel)} agents, {len(panel) * (len(panel) - 1) // 2} pairs, "
          f"{games} games/pair = {len(panel) * (len(panel) - 1) // 2 * games} battles "
          f"on {workers} workers")

    results, errors = _run_all(tasks, engine_dir, workers)
    total_errors = sum(errors.values())
    if total_errors:
        print(f"WARNING: {total_errors} battles failed to start")

    names = [Path(p).name for p in panel]
    by_name = {str(p): Path(p).name for p in panel}
    ratings = {n: Rating() for n in names}

    # Deterministic interleaved game sequence, so the fit is reproducible given the same results.
    seq = []
    pair_lists = {(by_name[a], by_name[b]): w for (a, b), w in results.items()}
    maxlen = max(len(v) for v in pair_lists.values())
    for i in range(maxlen):
        for (na, nb), wins in pair_lists.items():
            if i < len(wins):
                seq.append((na, nb, wins[i]))

    for p in range(max_passes):
        before = {n: r.mu for n, r in ratings.items()}
        for na, nb, a_won in seq:
            if a_won:
                ratings[na], ratings[nb] = rate_1vs1(ratings[na], ratings[nb], tau=0.0)
            else:
                ratings[nb], ratings[na] = rate_1vs1(ratings[nb], ratings[na], tau=0.0)
        delta = max(abs(ratings[n].mu - before[n]) for n in names)
        if delta < tol:
            print(f"converged after {p + 1} passes (max delta mu {delta:.4f})")
            break
    else:
        print(f"WARNING: no convergence in {max_passes} passes (max delta mu {delta:.4f})")

    win_matrix = {}
    for (na, nb), wins in pair_lists.items():
        win_matrix[f"{na}|{nb}"] = {"games": len(wins), "a_wins": sum(wins)}

    out = {
        "panel_version": panel_version(panel, games),
        "games_per_pair": games,
        "sigma_floor": PANEL_SIGMA_FLOOR,
        "params": {"mu0": DEFAULT_MU, "sigma0": DEFAULT_SIGMA, "beta": DEFAULT_BETA, "tau_fit": 0.0},
        "ratings": {
            n: {"mu": ratings[n].mu, "sigma": max(PANEL_SIGMA_FLOOR, ratings[n].sigma)}
            for n in names
        },
        "win_matrix": win_matrix,
        "errors": total_errors,
    }
    PANEL_RATINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PANEL_RATINGS_PATH.write_text(json.dumps(out, indent=2))

    print(f"\n{'panel agent':<44} {'mu':>8} {'sigma':>7}")
    for n in sorted(names, key=lambda k: ratings[k].mu, reverse=True):
        print(f"{n:<44} {ratings[n].mu:>8.1f} {max(PANEL_SIGMA_FLOOR, ratings[n].sigma):>7.1f}")
    print(f"\npanel_version {out['panel_version']} -> {PANEL_RATINGS_PATH}")
    return out


def load_panel_ratings() -> dict:
    if not PANEL_RATINGS_PATH.exists():
        raise SystemExit(
            f"No frozen panel at {PANEL_RATINGS_PATH}. Run:\n"
            f"    python3 src/ladder_eval.py fit-panel --games 2000"
        )
    return json.loads(PANEL_RATINGS_PATH.read_text())


def rate_candidate(candidate: Path, panel: list, games: int, workers: int,
                   dump_dir: str = None, exclude: set = None):
    """Play the candidate against every panel member (minus `exclude`) and rate it against the
    frozen panel ratings. Returns a result dict."""
    frozen = load_panel_ratings()
    exclude = exclude or set()
    opponents = [p for p in panel
                 if Path(p).name != candidate.name and Path(p).name not in exclude]
    missing = [Path(p).name for p in opponents if Path(p).name not in frozen["ratings"]]
    if missing:
        raise SystemExit(f"panel ratings missing for {missing}; re-run fit-panel")

    rb = _load_run_battle_module()
    engine_dir = rb.find_engine_dir(candidate, *panel)

    if dump_dir:
        Path(dump_dir).mkdir(parents=True, exist_ok=True)

    tasks = []
    for opp in opponents:
        tasks.extend(_chunk_tasks(candidate, opp, games, workers, dump_dir, "a"))
    results, errors = _run_all(tasks, engine_dir, workers)

    per_opponent, rows = {}, []
    total_wins = total_games = 0
    for opp in opponents:
        name = Path(opp).name
        wins = results.get((str(candidate), str(opp)), [])
        opp_rating = Rating.from_dict(frozen["ratings"][name])
        per_opponent[name] = [(opp_rating, w) for w in wins]
        n, k = len(wins), sum(wins)
        lo, hi = wilson_interval(k, n) if n else (0.0, 0.0)
        rows.append((name, k, n, errors.get((str(candidate), str(opp)), 0), lo, hi, opp_rating.mu))
        total_wins += k
        total_games += n

    rating = rate_against_fixed(Rating(), _interleave(per_opponent))
    pooled = total_wins / total_games if total_games else 0.0
    return {
        "candidate": candidate.name,
        "panel_version": frozen["panel_version"],
        "local_mu": rating.mu,
        "local_sigma": rating.sigma,
        "pooled_wr": pooled,
        "games": total_games,
        "rows": rows,
        "per_opponent": {k: (sum(w for _, w in v), len(v)) for k, v in per_opponent.items()},
    }


def print_result(res: dict, label: str = ""):
    head = f"{label} " if label else ""
    print(f"\n{head}{res['candidate']}  (panel {res['panel_version']})")
    print(f"{'opponent':<44} {'opp mu':>8} {'wins':>7} {'games':>7} {'err':>5} {'win%':>7} {'95% CI':>16}")
    for name, k, n, err, lo, hi, opp_mu in sorted(res["rows"], key=lambda r: -r[6]):
        pct = k / n * 100 if n else 0.0
        print(f"{name:<44} {opp_mu:>8.1f} {k:>7} {n:>7} {err:>5} {pct:>6.1f}% "
              f"[{lo * 100:>5.1f}, {hi * 100:>5.1f}]")
    lo, hi = wilson_interval(int(res["pooled_wr"] * res["games"]), res["games"])
    print(f"\n  local mu   {res['local_mu']:.1f}  (sigma {res['local_sigma']:.1f})   <- primary metric")
    print(f"  pooled WR  {res['pooled_wr'] * 100:.1f}%  95% CI [{lo * 100:.1f}, {hi * 100:.1f}]"
          f"  over {res['games']} games   <- reference only, biased by field composition")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    default_workers = max(1, min(8, (os.cpu_count() or 2) - 2))

    f = sub.add_parser("fit-panel", help="Round-robin the panel and freeze its ratings")
    f.add_argument("--games", type=int, default=2000, help="games per pair (default 2000)")
    f.add_argument("--workers", type=int, default=default_workers)
    f.add_argument("--panel", nargs="*", help="override the default panel")

    r = sub.add_parser("rate", help="Rate a candidate against the frozen panel")
    r.add_argument("--candidate", required=True)
    r.add_argument("--games", type=int, default=4000, help="games per opponent (default 4000)")
    r.add_argument("--workers", type=int, default=default_workers)
    r.add_argument("--panel", nargs="*")
    r.add_argument("--holdout", type=int, default=0,
                   help="reserve N panel members and report them separately (roster-overfit check)")
    r.add_argument("--dump-states", help="harvest the candidate's own trajectory states to this dir")
    r.add_argument("--json", help="also write the result dict here, for calibration_tracker.py")

    c = sub.add_parser("compare", help="Blocked head-to-head on an identical field")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.add_argument("--games", type=int, default=4000)
    c.add_argument("--workers", type=int, default=default_workers)
    c.add_argument("--panel", nargs="*")

    args = ap.parse_args()
    panel = [Path(p).resolve() for p in args.panel] if getattr(args, "panel", None) else DEFAULT_PANEL

    if args.cmd == "fit-panel":
        fit_panel(panel, args.games, args.workers)
        return

    if args.cmd == "rate":
        cand = Path(args.candidate).resolve()
        if args.holdout:
            held = {Path(p).name for p in panel[-args.holdout:]}
            seen = rate_candidate(cand, panel, args.games, args.workers,
                                  args.dump_states, exclude=held)
            print_result(seen, label="[seen field]")
            held_res = rate_candidate(
                cand, [p for p in panel if Path(p).name in held], args.games, args.workers)
            print_result(held_res, label="[held-out field]")
            gap = seen["local_mu"] - held_res["local_mu"]
            print(f"\n  seen-vs-heldout mu gap: {gap:+.1f}"
                  f"   (large positive => tuned to the panel, treat local mu as optimistic)")
        else:
            res = rate_candidate(cand, panel, args.games, args.workers, args.dump_states)
            print_result(res)
            if args.json:
                Path(args.json).parent.mkdir(parents=True, exist_ok=True)
                Path(args.json).write_text(json.dumps(res, indent=2))
        return

    if args.cmd == "compare":
        a, b = Path(args.a).resolve(), Path(args.b).resolve()
        block = {a.name, b.name}
        ra = rate_candidate(a, panel, args.games, args.workers, exclude=block)
        rb_ = rate_candidate(b, panel, args.games, args.workers, exclude=block)
        print_result(ra, label="[A]")
        print_result(rb_, label="[B]")
        print(f"\n  blocked field = panel minus {sorted(block)}")
        print(f"  mu:        A {ra['local_mu']:.1f}  vs  B {rb_['local_mu']:.1f}"
              f"   -> {'A' if ra['local_mu'] > rb_['local_mu'] else 'B'} ahead by "
              f"{abs(ra['local_mu'] - rb_['local_mu']):.1f}")
        print(f"  pooled WR: A {ra['pooled_wr'] * 100:.1f}%  vs  B {rb_['pooled_wr'] * 100:.1f}%")


if __name__ == "__main__":
    main()
