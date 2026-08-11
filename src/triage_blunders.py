"""Sort/dedupe PIMC-oracle blunder records into a root-cause worklist.

Run:
    python3 src/triage_blunders.py \\
        data/processed/instrumentation/blunders_crustle.jsonl:crustle \\
        data/processed/instrumentation/blunders_alakazam.jsonl:alakazam \\
        --out data/processed/instrumentation/blunder_worklist.json
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_losses(path):
    """Loss-game records with a computed gap, the only ones triage cares about."""
    recs = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return [r for r in recs if r["game_result"] == "loss" and r.get("gap") is not None]


def bucket_key(turn):
    return turn // 2 if turn is not None else "unknown"


def build_worklist(sources):
    """`sources` is [(path, matchup_label), ...]. Returns the sorted, deduped worklist."""
    buckets = defaultdict(lambda: {"gap": float("-inf"), "count": 0, "example_game_ids": []})
    for path, matchup in sources:
        for rec in load_losses(path):
            key = (matchup, bucket_key(rec["turn"]))
            b = buckets[key]
            b["count"] += 1
            if len(b["example_game_ids"]) < 3:
                b["example_game_ids"].append(rec["game_id"])
            if rec["gap"] > b["gap"]:
                b["gap"] = rec["gap"]
                b["turn"] = rec["turn"]
                b["chosen_option"] = rec["chosen_option"]
                b["best_alt_option"] = rec["best_alt_option"]

    worklist = []
    for (matchup, _), b in buckets.items():
        worklist.append({
            "matchup": matchup,
            "gap": b["gap"],
            "turn": b.get("turn"),
            "count": b["count"],
            "example_game_ids": b["example_game_ids"],
            "chosen_option": b.get("chosen_option"),
            "best_alt_option": b.get("best_alt_option"),
        })
    worklist.sort(key=lambda w: w["gap"], reverse=True)
    return worklist


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+", help="path:matchup_label pairs")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    sources = []
    for s in args.sources:
        path, _, label = s.partition(":")
        sources.append((path, label or Path(path).stem))
    worklist = build_worklist(sources)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(worklist, indent=2))
    print(f"{len(worklist)} distinct decision buckets -> {args.out}")
    for w in worklist[:10]:
        print(f"  gap={w['gap']:.3f} matchup={w['matchup']} turn={w['turn']} "
              f"count={w['count']} chosen={w['chosen_option']} alt={w['best_alt_option']}")


if __name__ == "__main__":
    main()
