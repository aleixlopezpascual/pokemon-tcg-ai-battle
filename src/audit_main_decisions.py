"""MAIN-decision auditor — replay dumped states through a real agent and measure its own scores.

This is a measurement task, not a policy change. It decides which lever the rest of the plan
pulls next by reporting, for a candidate's own MAIN-context decisions:

- a margin histogram (how close the top option was to the best option of a *different* type),
- a tie-multiplicity report (how often the agent's own ranking has an outright tie at the top,
  and whether that tie is within one option class or across classes),
- the chosen-vs-available option-class mix, to compare against a measured expert corpus.

Score capture, without duplicating the scoring loop: a candidate's per-option scores are local to
its own `_agent`-style dispatch, and re-implementing that dispatch here would silently drift from
the real agent. Instead this exploits the fact that `submissions/soutasakurai_libraryout_crustle/
main.py` contains exactly one `sorted(` call, at line 1233 (confirmed: 1,256 lines total). Python
resolves a bare `sorted` through module globals *before* builtins, so injecting a probe into the
loaded module's `__dict__` intercepts that one call and nothing else.
"""
import argparse
import builtins
import glob
import hashlib
import json
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder_eval  # noqa: E402

MARGIN_BUCKETS = ("0", "1-99", "100-999", "1000-4999", ">=5000", "single-class")


@contextmanager
def score_probe(module):
    """Capture the per-option score vector from main.py:1233's single sorted() call.

    Verified: main.py contains exactly one `sorted(` call, at line 1233, so this
    intercepts that call and no other. Python resolves a bare `sorted` through module
    globals before builtins, so injecting the name here shadows it for this module only.
    """
    captured = []

    def probe(iterable, *, key=None, reverse=False):
        items = list(iterable)
        if key is not None:
            captured.append([key(i) for i in items])
        return builtins.sorted(items, key=key, reverse=reverse)

    module.__dict__["sorted"] = probe
    try:
        yield captured
    finally:
        module.__dict__.pop("sorted", None)


def _load_module(agent_dir: Path):
    """Load `agent_dir`'s main.py in isolation and return (agent_fn, module).

    Mirrors `ladder_eval._get`'s module-name scheme (a stable hash of the agent dir, since a
    Python `hash()` is salted per-process) so the loaded module can be found again in
    `sys.modules` afterward. `_load_agent_isolated` needs `ladder_eval._W["rb"]`, which is only
    populated by `ladder_eval._worker_init` — this driver process is not a pool worker, so that
    must be called here first.
    """
    agent_dir = agent_dir.resolve()
    rb = ladder_eval._load_run_battle_module()
    engine_dir = rb.find_engine_dir(agent_dir, ladder_eval.DEFAULT_PANEL[0])
    ladder_eval._worker_init(str(engine_dir))
    module_name = "audit_" + hashlib.sha256(str(agent_dir).encode()).hexdigest()[:12]
    agent_fn = ladder_eval._load_agent_isolated(agent_dir, module_name)
    module = sys.modules[module_name]
    return agent_fn, module


def replay_decisions(agent_dir, states_glob: str, limit=None, stats: dict | None = None) -> Iterator[dict]:
    """Replay dumped MAIN-context decision states through `agent_dir`'s real agent.

    Yields one dict per eligible record (`select["context"] == 0`, `select["maxCount"] == 1`,
    `len(select["option"]) > 1`) with the agent's own captured score vector and derived fields.

    `stats`, if given, is updated in place with `examined`, `eligible`, `degraded` (the probe
    captured nothing — the agent took its `select is None` or `except` fallback path) and
    `no_choice` (the agent returned an empty selection despite scoring normally) counts. A
    nonzero `degraded` means the audit is measuring a degraded agent and must be investigated
    before its numbers are used.
    """
    agent_fn, module = _load_module(Path(agent_dir))
    if stats is None:
        stats = {}
    stats.setdefault("examined", 0)
    stats.setdefault("eligible", 0)
    stats.setdefault("degraded", 0)
    stats.setdefault("no_choice", 0)

    yielded = 0
    for path in sorted(glob.glob(states_glob)):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                stats["examined"] += 1
                select = rec["select"]
                if (select.get("context") != 0
                        or select.get("maxCount") != 1
                        or len(select.get("option") or []) <= 1):
                    continue
                stats["eligible"] += 1

                obs_dict = {"select": rec["select"], "current": rec["current"], "logs": []}
                with score_probe(module) as captured:
                    chosen = agent_fn(obs_dict)

                if not captured:
                    stats["degraded"] += 1
                    continue
                if not chosen:
                    stats["no_choice"] += 1
                    continue

                scores = captured[-1]
                types = [opt["type"] for opt in select["option"]]
                top = max(scores)
                top_idx = scores.index(top)  # first occurrence == stable-sort tie-break winner
                top_type = types[top_idx]
                chosen_idx = chosen[0]
                chosen_class = types[chosen_idx]
                avail = set(types)

                other_class_scores = [s for s, t in zip(scores, types) if t != top_type]
                cross_class_margin = (top - max(other_class_scores)) if other_class_scores else float("inf")

                top_tie_n = sum(1 for s in scores if s == top)
                tie_classes = {t for s, t in zip(scores, types) if s == top}

                yield {
                    "scores": scores,
                    "types": types,
                    "top": top,
                    "chosen_idx": chosen_idx,
                    "chosen_class": chosen_class,
                    "avail": avail,
                    "cross_class_margin": cross_class_margin,
                    "top_tie_n": top_tie_n,
                    "tie_classes": tie_classes,
                }
                yielded += 1
                if limit is not None and yielded >= limit:
                    return


def _margin_bucket(margin: float) -> str:
    if margin == float("inf"):
        return "single-class"
    if margin == 0:
        return "0"
    if margin < 100:
        return "1-99"
    if margin < 1000:
        return "100-999"
    if margin < 5000:
        return "1000-4999"
    return ">=5000"


def margin_histogram(decisions) -> dict:
    hist = {b: 0 for b in MARGIN_BUCKETS}
    for d in decisions:
        hist[_margin_bucket(d["cross_class_margin"])] += 1
    return hist


def tie_report(decisions) -> dict:
    multiplicity = Counter()
    within_class = Counter()
    cross_class = 0
    for d in decisions:
        n = d["top_tie_n"]
        multiplicity[n] += 1
        if n > 1:
            if len(d["tie_classes"]) == 1:
                (opt_type,) = d["tie_classes"]
                within_class[opt_type] += 1
            else:
                cross_class += 1
    return {
        "multiplicity": dict(multiplicity),
        "within_class": dict(within_class),
        "cross_class": cross_class,
    }


def class_mix(decisions) -> dict:
    decisions = list(decisions)
    n = len(decisions)
    chosen = Counter(d["chosen_class"] for d in decisions)
    available = Counter()
    for d in decisions:
        for t in d["avail"]:
            available[t] += 1
    return {
        "chosen": {t: c / n for t, c in chosen.items()} if n else {},
        "available": {t: c / n for t, c in available.items()} if n else {},
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", required=True)
    p.add_argument("--states", required=True, help="glob for dumped shard files")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--json")
    args = p.parse_args()

    stats: dict = {}
    decisions = list(replay_decisions(Path(args.candidate), args.states, args.limit, stats))

    hist = margin_histogram(decisions)
    ties = tie_report(decisions)
    mix = class_mix(decisions)

    print(f"decisions: {len(decisions)} (examined={stats['examined']} eligible={stats['eligible']} "
          f"degraded={stats['degraded']} no_choice={stats['no_choice']})")
    if stats["degraded"]:
        print(f"WARNING: {stats['degraded']} records hit the agent's exception/None-select "
              f"fallback path — this audit is measuring a partially degraded agent.")

    print("\nmargin_histogram:")
    for b in MARGIN_BUCKETS:
        print(f"  {b}: {hist[b]}")

    print("\ntie_report:")
    print(f"  multiplicity: {dict(sorted(ties['multiplicity'].items()))}")
    print(f"  within_class: {ties['within_class']}")
    print(f"  cross_class: {ties['cross_class']}")

    print("\nclass_mix (chosen):")
    for t, share in sorted(mix["chosen"].items(), key=lambda kv: -kv[1]):
        print(f"  {t}: {share:.4f}")
    print("class_mix (available):")
    for t, share in sorted(mix["available"].items(), key=lambda kv: -kv[1]):
        print(f"  {t}: {share:.4f}")

    if args.json:
        out = {
            "stats": stats,
            "margin_histogram": hist,
            "tie_report": {
                "multiplicity": {str(k): v for k, v in ties["multiplicity"].items()},
                "within_class": {str(k): v for k, v in ties["within_class"].items()},
                "cross_class": ties["cross_class"],
            },
            "class_mix": {
                "chosen": {str(k): v for k, v in mix["chosen"].items()},
                "available": {str(k): v for k, v in mix["available"].items()},
            },
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
