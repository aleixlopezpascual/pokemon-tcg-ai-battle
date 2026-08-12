"""Tests for `src/deck_meta.py`.

Run: python3 src/test_deck_meta.py

Same convention as `test_trueskill_lite.py` and `test_instrument_agent.py`: a plain script, no
pytest, every numeric claim re-derived here rather than copied from the implementation.

The clustering tests matter most. A deck is a *multiset* — `[5, 5, 13]` is two copies of card 5,
not one — so set-based Jaccard would call a 4-copy Ultra Ball list identical to a 1-copy list and
silently merge two different archetypes into one cluster.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deck_meta import (  # noqa: E402
    Cluster,
    cluster_decks,
    dedupe_episode_sides,
    jaccard,
    score_band,
)

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    status = "ok" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def test_jaccard_identical_decks_is_one():
    print("jaccard is 1.0 for a deck against itself")
    deck = [1, 1, 2, 3]
    check("identical", jaccard(deck, deck) == 1.0, f"got {jaccard(deck, deck)}")
    check("disjoint is 0.0", jaccard([1, 2], [3, 4]) == 0.0)


def test_jaccard_respects_copy_counts():
    print("jaccard treats a deck as a multiset, not a set")
    four_copies = [7, 7, 7, 7]
    one_copy = [7]
    # Independent derivation: intersection multiset is {7:1}, union multiset is {7:4}, so 1/4.
    check("4 copies vs 1 copy is 0.25", jaccard(four_copies, one_copy) == 0.25,
          f"got {jaccard(four_copies, one_copy)}")
    check("set-based Jaccard would wrongly say 1.0",
          jaccard(four_copies, one_copy) != 1.0)


def test_jaccard_partial_overlap():
    print("partial overlap matches a hand-computed value")
    a = [1, 1, 2, 3]
    b = [1, 2, 2, 4]
    # min counts: 1->1, 2->1  => 2 ; max counts: 1->2, 2->2, 3->1, 4->1 => 6
    check("2/6", abs(jaccard(a, b) - 2 / 6) < 1e-12, f"got {jaccard(a, b)}")
    check("symmetric", jaccard(a, b) == jaccard(b, a))


def test_dedupe_keeps_one_row_per_episode_side():
    print("one row survives per (episode_id, player)")
    rows = [
        {"episode_id": "e1", "player": 0, "actor_deck": [1], "actor_reward": 1},
        {"episode_id": "e1", "player": 0, "actor_deck": [1], "actor_reward": 1},
        {"episode_id": "e1", "player": 1, "actor_deck": [2], "actor_reward": -1},
    ]
    kept = list(dedupe_episode_sides(rows))
    check("2 rows kept", len(kept) == 2, f"got {len(kept)}")
    keys = {(r["episode_id"], r["player"]) for r in kept}
    check("both sides present", keys == {("e1", 0), ("e1", 1)}, f"got {keys}")


def test_cluster_groups_near_identical_decks():
    print("near-identical decks land in one cluster, a different deck in another")
    base = [1] * 30 + [2] * 30
    tweaked = [1] * 29 + [2] * 30 + [3]          # one card swapped
    other = [9] * 30 + [8] * 30                   # nothing in common
    rows = [
        {"episode_id": "a", "player": 0, "actor_deck": base, "actor_reward": 1,
         "actor_team": "T1", "actor_score": 1100.0, "opp_score": 900.0},
        {"episode_id": "b", "player": 0, "actor_deck": tweaked, "actor_reward": -1,
         "actor_team": "T2", "actor_score": 1050.0, "opp_score": 900.0},
        {"episode_id": "c", "player": 0, "actor_deck": other, "actor_reward": 1,
         "actor_team": "T3", "actor_score": 700.0, "opp_score": 900.0},
    ]
    clusters = cluster_decks(rows, threshold=0.7)
    check("2 clusters", len(clusters) == 2, f"got {len(clusters)}")
    big = max(clusters, key=lambda c: c.games)
    check("big cluster has 2 games", big.games == 2, f"got {big.games}")
    check("big cluster has 1 win", big.wins == 1, f"got {big.wins}")
    check("big cluster has both teams", big.teams == {"T1", "T2"}, f"got {big.teams}")
    check("mean score is the plain mean", abs(big.mean_score - 1075.0) < 1e-9,
          f"got {big.mean_score}")
    check("representative deck has 60 cards", len(big.representative_deck) == 60,
          f"got {len(big.representative_deck)}")


def test_cluster_threshold_is_respected():
    print("a below-threshold deck is not merged")
    a = [1] * 60
    b = [1] * 30 + [2] * 30      # jaccard = 30/90 = 0.333
    rows = [
        {"episode_id": "a", "player": 0, "actor_deck": a, "actor_reward": 1,
         "actor_team": "T1", "actor_score": 1000.0, "opp_score": 1000.0},
        {"episode_id": "b", "player": 0, "actor_deck": b, "actor_reward": 1,
         "actor_team": "T2", "actor_score": 1000.0, "opp_score": 1000.0},
    ]
    check("split at threshold 0.5", len(cluster_decks(rows, threshold=0.5)) == 2)
    check("merged at threshold 0.3", len(cluster_decks(rows, threshold=0.3)) == 1)


def test_win_rate_and_reward_convention():
    print("a win is actor_reward > 0, and win rate divides by games")
    rows = [
        {"episode_id": str(i), "player": 0, "actor_deck": [1] * 60,
         "actor_reward": r, "actor_team": "T", "actor_score": 1000.0, "opp_score": 1000.0}
        for i, r in enumerate([1, 1, -1, 0])
    ]
    c = cluster_decks(rows, threshold=0.9)[0]
    check("4 games", c.games == 4, f"got {c.games}")
    check("2 wins (reward 0 is not a win)", c.wins == 2, f"got {c.wins}")
    check("win rate 0.5", abs(c.win_rate - 0.5) < 1e-12, f"got {c.win_rate}")


def test_score_band_edges():
    print("score bands are half-open and cover the range")
    edges = [800, 1000, 1200]
    check("below first edge", score_band(700.0, edges) == "<800")
    check("on an edge goes up", score_band(1000.0, edges) == "1000-1200")
    check("inside a band", score_band(999.9, edges) == "800-1000")
    check("above last edge", score_band(1500.0, edges) == ">=1200")
    check("missing score", score_band(None, edges) == "unknown")


if __name__ == "__main__":
    for fn in (
        test_jaccard_identical_decks_is_one,
        test_jaccard_respects_copy_counts,
        test_jaccard_partial_overlap,
        test_dedupe_keeps_one_row_per_episode_side,
        test_cluster_groups_near_identical_decks,
        test_cluster_threshold_is_respected,
        test_win_rate_and_reward_convention,
        test_score_band_edges,
    ):
        fn()
        print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print("all tests passed")
