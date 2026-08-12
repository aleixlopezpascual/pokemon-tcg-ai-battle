"""Lever L6, Step 1 -- cluster the harvested corpus once, then match every existing submission's
deck against the resulting clusters, before spending any battle budget.

Context: L0 (Task 5), L0b (Task 6), and L5 (Task 10 so far) all FAILED a cheap reachability check
before touching agent code or running a single battle -- three consecutive zero-ML levers. Per the
plan's lever table, L5 failing routes here: "deck mining, not policy imitation... needs no IL to
work at all." The plan's L6 row cites specific numbers (cluster 6 at 288 sides/64.6% WR matching
`kiyota_mega_lucario_ex`; cluster 16 at 47 sides/63.8% WR) but those were computed in an earlier,
uncaptured session and never persisted anywhere in this repo -- this script re-derives the clusters
live rather than assuming those numbers or those two archetypes are the right ones.

Pure measurement: streams `data/processed/il_records_v3_combined.jsonl` (2.9 GB) exactly once via
`deck_meta.stream_records` (never loaded whole), clusters with `deck_meta.cluster_decks`, then does
the per-submission Jaccard matching (`deck_meta.jaccard`, multiset -- not set-based, since copy
counts define archetypes) as cheap in-memory work against every `submissions/*/deck.csv` found on
disk (no hardcoded submission list). No agent code is touched, no battles are run.

Gates applied, straight from the plan's L6 row and this project's established floors:
- Cluster sample-size floor: games >= 30 (below this a win rate is too noisy to act on).
- Cluster win-rate floor: win_rate >= 0.60 (this plan's "high-WR" bar, matching the plan's own
  L6 spec language "64.6%"/"63.8%").
- Match floor: jaccard(cluster.representative_deck, submission_deck) >= 0.6.
- Rating floor for corpus rows: actor_score >= 1100, the same "strong player" floor Task 7 used.

Usage:
    python3 src/measure_deck_cluster_candidates.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_meta  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDS_PATH = REPO_ROOT / "data/processed/il_records_v3_combined.jsonl"
OUT_JSON = REPO_ROOT / "data/processed/instrumentation/deck_cluster_candidates.json"

ACTOR_SCORE_FLOOR = 1100  # same "strong player" rating floor Task 7 used
CLUSTER_THRESHOLD = 0.7  # deck_meta.cluster_decks default
MIN_GAMES = 30  # sample-size floor: below this a win rate is too noisy to act on
MIN_WIN_RATE = 0.60  # this plan's "high-WR" bar (matches L6 row's "64.6%"/"63.8%")
MATCH_JACCARD_FLOOR = 0.6  # "a match is jaccard >= 0.6"


def main() -> int:
    if not RECORDS_PATH.exists():
        print(f"SKIP: corpus file not found at {RECORDS_PATH}")
        return 1

    print(f"streaming {RECORDS_PATH} (this is the one and only pass over the 2.9GB file)...")
    rows = deck_meta.stream_records(RECORDS_PATH)
    rows = (r for r in rows
            if r.get("actor_score") is not None and r["actor_score"] >= ACTOR_SCORE_FLOOR)
    clusters = deck_meta.cluster_decks(rows, threshold=CLUSTER_THRESHOLD)
    print(f"clustered into {len(clusters)} clusters "
          f"(actor_score >= {ACTOR_SCORE_FLOOR}, threshold {CLUSTER_THRESHOLD})")

    qualifying = [c for c in clusters if c.games >= MIN_GAMES and c.win_rate >= MIN_WIN_RATE]
    print(f"qualifying clusters (games >= {MIN_GAMES}, win_rate >= {MIN_WIN_RATE:.0%}): "
          f"{len(qualifying)} of {len(clusters)}")
    for i, c in enumerate(qualifying):
        print(f"  cluster games={c.games:>5} wins={c.wins:>5} win_rate={c.win_rate * 100:>5.1f}%  "
              f"teams={len(c.teams):>3}  mean_score={c.mean_score:>7.1f}")

    deck_paths = sorted(REPO_ROOT.glob("submissions/*/deck.csv"))
    print(f"\nfound {len(deck_paths)} submissions/*/deck.csv files to match against")

    matches = []
    for deck_path in deck_paths:
        submission = deck_path.parent.name
        try:
            sub_deck = deck_meta.load_deck_csv(deck_path)
        except (OSError, ValueError) as exc:
            print(f"  SKIP {submission}: could not load deck.csv ({exc})")
            continue
        for rank, cluster in enumerate(qualifying):
            j = deck_meta.jaccard(cluster.representative_deck, sub_deck)
            if j >= MATCH_JACCARD_FLOOR:
                matches.append({
                    "submission": submission,
                    "cluster_rank": rank,
                    "games": cluster.games,
                    "wins": cluster.wins,
                    "win_rate": cluster.win_rate,
                    "mean_score": cluster.mean_score,
                    "jaccard": j,
                    "representative_deck": cluster.representative_deck,
                })

    matches.sort(key=lambda m: m["win_rate"], reverse=True)

    print(f"\nmatches (jaccard >= {MATCH_JACCARD_FLOOR}) against qualifying clusters: {len(matches)}")
    if matches:
        header = (f"{'submission':<45} {'cluster':>7} {'games':>6} {'win%':>6} "
                  f"{'mean_score':>10} {'jaccard':>7}")
        print(header)
        for m in matches:
            print(f"{m['submission']:<45} {m['cluster_rank']:>7} {m['games']:>6} "
                  f"{m['win_rate'] * 100:>5.1f}% {m['mean_score']:>10.1f} {m['jaccard']:>7.3f}")
    else:
        print("NO CANDIDATES: no (submission, cluster) pair cleared both the cluster floor "
              f"(games >= {MIN_GAMES}, win_rate >= {MIN_WIN_RATE:.0%}) and the match floor "
              f"(jaccard >= {MATCH_JACCARD_FLOOR}). L6 has no reachable target on this corpus pass.")

    result = {
        "records_path": str(RECORDS_PATH),
        "actor_score_floor": ACTOR_SCORE_FLOOR,
        "cluster_threshold": CLUSTER_THRESHOLD,
        "min_games": MIN_GAMES,
        "min_win_rate": MIN_WIN_RATE,
        "match_jaccard_floor": MATCH_JACCARD_FLOOR,
        "total_clusters": len(clusters),
        "qualifying_clusters": [c.to_dict() for c in qualifying],
        "submissions_checked": [p.parent.name for p in deck_paths],
        "matches": matches,
        "verdict": "CANDIDATES_FOUND" if matches else "NO_CANDIDATES",
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {OUT_JSON}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
