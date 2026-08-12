"""Parallel A-vs-B mirror head-to-head. The within-archetype gate instrument.

The frozen panel cannot screen within-archetype tweaks (see evaluation-methodology.md's
2026-08-09 retro-validation). This is what settles them locally.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder_eval
from local_eval import wilson_interval


def mirror(a_dir, b_dir, games: int, workers: int) -> dict:
    a_dir, b_dir = Path(a_dir).resolve(), Path(b_dir).resolve()
    rb = ladder_eval._load_run_battle_module()
    engine_dir = rb.find_engine_dir(a_dir, b_dir, ladder_eval.DEFAULT_PANEL[0])
    tasks = ladder_eval._chunk_tasks(a_dir, b_dir, games, workers)
    results, errors = ladder_eval._run_all(tasks, engine_dir, workers)
    key = (str(a_dir), str(b_dir))
    outcomes = results.get(key, [])
    wins, n = sum(1 for w in outcomes if w), len(outcomes)
    lo, hi = wilson_interval(wins, n) if n else (0.0, 0.0)
    return {"a": str(a_dir), "b": str(b_dir), "wins": wins, "games": n,
            "errors": errors.get(key, 0), "wr": wins / n if n else 0.0,
            "lo": lo, "hi": hi}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--games", type=int, default=4000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--json")
    args = p.parse_args()
    r = mirror(args.a, args.b, args.games, args.workers)
    print(f"{r['a']} vs {r['b']}: {r['wins']}/{r['games']} "
          f"({100*r['wr']:.2f}%) 95% CI [{100*r['lo']:.2f}, {100*r['hi']:.2f}] errors={r['errors']}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
