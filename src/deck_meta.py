"""Mine harvested episode records for decklists and win rates, banded by opponent strength.

Our archetype choice rests on a 5-week-old snapshot, and the top of this ladder is documented to
cycle decks on roughly a one-day cadence (#729926). This asks the on-disk episodes a narrower
question: which decklists are actually being played by high-scoring teams right now, and how do
they do against each other.

Decklists are permitted data. A deck is 60 integers, published by the host in public episodes
(#709320, Addison Howard) — unlike agent source, which is not ours to take.

Two things this deliberately does not do:

- It never loads the file into memory. The v3 record file is 2.9 GB and every decision record in
  an episode repeats that episode's full deck, so the useful content is a few thousand rows hiding
  inside millions.
- It does not treat a deck as a set. Copy counts are the difference between archetypes: a 4-copy
  Ultra Ball list and a 1-copy list are different decks, and set Jaccard scores them identical.

Usage:
    python3 src/deck_meta.py --records data/processed/il_records_2026-08-05_v3.jsonl \\
        --min-score 1000 --compare submissions/masamikobayashi_archaludon_cinderace/deck.csv
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BANDS = [800, 1000, 1200]


def jaccard(deck_a, deck_b) -> float:
    """Multiset Jaccard: sum of per-card minimums over sum of per-card maximums.

    Multiset, not set — see the module docstring. Two empty decks are defined as 0.0 rather than
    1.0 so a malformed row cannot silently match everything.
    """
    a = deck_a if isinstance(deck_a, Counter) else Counter(deck_a)
    b = deck_b if isinstance(deck_b, Counter) else Counter(deck_b)
    if not a or not b:
        return 0.0
    keys = a.keys() | b.keys()
    inter = sum(min(a[k], b[k]) for k in keys)
    union = sum(max(a[k], b[k]) for k in keys)
    return inter / union if union else 0.0


def score_band(score, edges=None) -> str:
    """Label a score with a half-open band, `edges` ascending. `None` scores are kept, not dropped —
    a missing score is a fact about the harvest, and silently discarding those rows would bias the
    banded win rates toward whatever populations happen to carry a score."""
    edges = edges or DEFAULT_BANDS
    if score is None:
        return "unknown"
    if score < edges[0]:
        return f"<{edges[0]}"
    for lo, hi in zip(edges, edges[1:]):
        if lo <= score < hi:
            return f"{lo}-{hi}"
    return f">={edges[-1]}"


def dedupe_episode_sides(rows):
    """Yield the first row seen for each `(episode_id, player)`.

    Every decision record in an episode carries the same `actor_deck`, `actor_team` and
    `actor_reward`, so counting rows would weight each episode by how many decisions it happened
    to contain — long games would dominate the meta picture for no reason.
    """
    seen = set()
    for row in rows:
        key = (row.get("episode_id"), row.get("player"))
        if key in seen:
            continue
        seen.add(key)
        yield row


def stream_records(path: Path):
    """Yield only the fields this analysis needs, one line at a time.

    Parses each line fully (the records are not shaped for partial parsing) but keeps only the
    small projection, so peak memory stays proportional to the number of distinct episode sides
    rather than to the 2.9 GB file.
    """
    with path.open() as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # a truncated final line from an interrupted harvest
            deck = rec.get("actor_deck")
            if not deck:
                continue
            yield {
                "episode_id": rec.get("episode_id"),
                "player": rec.get("player"),
                "actor_deck": deck,
                "actor_team": rec.get("actor_team"),
                "actor_score": rec.get("actor_score"),
                "opp_team": rec.get("opp_team"),
                "opp_score": rec.get("opp_score"),
                "actor_reward": rec.get("actor_reward"),
                "_lineno": lineno,
            }


class Cluster:
    """A group of near-identical decklists and the record of how they did."""

    def __init__(self, deck):
        self.counter = Counter(deck)
        self.representative_deck = sorted(deck)
        self.teams = set()
        self.games = 0
        self.wins = 0
        self._score_sum = 0.0
        self._score_n = 0
        self._opp_score_sum = 0.0
        self._opp_score_n = 0
        self.band_games = Counter()
        self.band_wins = Counter()

    def add(self, row):
        self.games += 1
        if (row.get("actor_reward") or 0) > 0:
            self.wins += 1
        team = row.get("actor_team")
        if team:
            self.teams.add(team)
        score = row.get("actor_score")
        if score is not None:
            self._score_sum += score
            self._score_n += 1
        opp = row.get("opp_score")
        if opp is not None:
            self._opp_score_sum += opp
            self._opp_score_n += 1
        band = score_band(opp)
        self.band_games[band] += 1
        if (row.get("actor_reward") or 0) > 0:
            self.band_wins[band] += 1

    @property
    def mean_score(self) -> float:
        return self._score_sum / self._score_n if self._score_n else 0.0

    @property
    def mean_opp_score(self) -> float:
        return self._opp_score_sum / self._opp_score_n if self._opp_score_n else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    def to_dict(self) -> dict:
        return {
            "games": self.games,
            "wins": self.wins,
            "win_rate": self.win_rate,
            "teams": sorted(self.teams),
            "team_count": len(self.teams),
            "mean_score": self.mean_score,
            "mean_opp_score": self.mean_opp_score,
            "by_opponent_band": {
                band: {
                    "games": n,
                    "win_rate": self.band_wins[band] / n if n else 0.0,
                }
                for band, n in sorted(self.band_games.items())
            },
            "deck": self.representative_deck,
        }


def cluster_decks(rows, threshold: float = 0.7):
    """Greedy single-pass clustering against each cluster's first-seen representative.

    Greedy rather than hierarchical because the input is already tightly grouped — real decklists
    are near-duplicates of a handful of archetypes, not a continuum — and a greedy pass is O(rows x
    clusters) instead of O(rows^2). The consequence to be aware of: cluster membership depends on
    which deck is seen first, so a chain of 0.69-similar decks can end up split. Raise or lower
    `--threshold` and see whether the picture is stable before drawing a conclusion from it.
    """
    clusters: list[Cluster] = []
    for row in dedupe_episode_sides(rows):
        deck = row["actor_deck"]
        counter = Counter(deck)
        best, best_sim = None, 0.0
        for cluster in clusters:
            sim = jaccard(counter, cluster.counter)
            if sim > best_sim:
                best, best_sim = cluster, sim
        if best is not None and best_sim >= threshold:
            best.add(row)
        else:
            fresh = Cluster(deck)
            fresh.add(row)
            clusters.append(fresh)
    clusters.sort(key=lambda c: c.games, reverse=True)
    return clusters


def load_deck_csv(path: Path) -> list[int]:
    return [int(line) for line in path.read_text().split("\n") if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True)
    parser.add_argument("--min-score", type=float, default=None,
                        help="Only count episode sides whose actor_score is at least this.")
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--min-games", type=int, default=3,
                        help="Suppress clusters with fewer games than this from the report.")
    parser.add_argument("--compare", help="A deck.csv to report Jaccard against every cluster.")
    parser.add_argument("--json", help="Write the full report here.")
    args = parser.parse_args()

    records = stream_records(Path(args.records))
    if args.min_score is not None:
        records = (r for r in records
                   if r.get("actor_score") is not None and r["actor_score"] >= args.min_score)

    clusters = cluster_decks(records, threshold=args.threshold)

    compare_deck = load_deck_csv(Path(args.compare)) if args.compare else None
    report = {
        "records": args.records,
        "min_score": args.min_score,
        "threshold": args.threshold,
        "episode_sides": sum(c.games for c in clusters),
        "distinct_teams": len({t for c in clusters for t in c.teams}),
        "clusters": [],
    }

    print(f"episode sides: {report['episode_sides']}   "
          f"distinct teams: {report['distinct_teams']}   "
          f"clusters: {len(clusters)}")
    if compare_deck is not None:
        print(f"comparing against {args.compare}")
    print()
    header = f"{'#':>3}  {'games':>6}  {'teams':>5}  {'win%':>6}  {'mean mu':>8}  {'opp mu':>7}"
    if compare_deck is not None:
        header += f"  {'jaccard':>7}"
    print(header)

    for i, cluster in enumerate(clusters):
        entry = cluster.to_dict()
        if compare_deck is not None:
            entry["jaccard_vs_compare"] = jaccard(cluster.representative_deck, compare_deck)
        report["clusters"].append(entry)
        if cluster.games < args.min_games:
            continue
        line = (f"{i:>3}  {cluster.games:>6}  {len(cluster.teams):>5}  "
                f"{cluster.win_rate * 100:>5.1f}%  {cluster.mean_score:>8.1f}  "
                f"{cluster.mean_opp_score:>7.1f}")
        if compare_deck is not None:
            line += f"  {entry['jaccard_vs_compare']:>7.3f}"
        print(line)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
