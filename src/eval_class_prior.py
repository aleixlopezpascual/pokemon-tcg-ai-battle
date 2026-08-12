"""Task 8: offline trainer + three pre-registered go/no-go gates for the class-prior lever.

Trains a 7-class MAIN-decision-type classifier (PLAY/ATTACH/EVOLVE/ABILITY/RETREAT/ATTACK/END,
`OptionType` ints from `features.py`) on `data/processed/main_class_pooled_1100.jsonl` (the Task 7
fallback dataset -- the deck-scoped Crustle variant came in at 4,445 rows, under Task 7's own
~5,000-row underpowered threshold, so the pooled corpus at floor 1100 is used instead, with each
row's `side_jaccard` -- its own Crustle deck-jaccard -- carried as an extra input feature rather
than a hard filter).

Mirrors `train_intent_classifier.py`'s setup: `HistGradientBoostingClassifier(max_iter=300,
max_depth=6, learning_rate=0.08, class_weight="balanced", random_state=0)`,
`GroupShuffleSplit(test_size=0.2, random_state=0)` grouped on `episode_id`.

Three pre-registered gates, run in order, ALL must pass or the whole class-prior lever is
abandoned (no agent code touched):

- G3a (informativeness): masked top-1 accuracy on a random 20% held-out split must beat
  `availability_baseline` (the per-decision "most common *legal* class" heuristic) by >= 5.0pp.
- G3b (transfer): retrain holding out one whole deck cluster (mined from the same floor-1100
  population via `deck_meta.cluster_decks`); masked top-1 on the held-out cluster's decisions
  must retain >= 60% of G3a's in-distribution lift.
- G3c (disagreement): on Task 3's replayed Crustle self-play states
  (`data/processed/selfplay_crustle/shard_*.jsonl`), the G3a model's masked argmax must disagree
  with Crustle's actual chosen class on 8-35% of decisions.

Usage:
    python3 src/eval_class_prior.py
"""

import argparse
import glob
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_meta  # noqa: E402
from build_main_class_dataset import (  # noqa: E402
    _is_eligible_record,
    _passes_rating,
    decision_features,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RECORDS = REPO_ROOT / "data" / "processed" / "main_class_pooled_1100.jsonl"
DEFAULT_RAW_CORPUS = REPO_ROOT / "data" / "processed" / "il_records_v3_combined.jsonl"
DEFAULT_SELFPLAY_GLOB = str(REPO_ROOT / "data" / "processed" / "selfplay_crustle" / "shard_*.jsonl")
DEFAULT_DECK_REF = REPO_ROOT / "submissions" / "crustle_il" / "deck.csv"
DEFAULT_OUT = REPO_ROOT / "models" / "class_prior_crustle.pkl"

# `decision_features`'s 35 columns (24 `global_features` + 11 availability/lethality columns),
# in the same order `features.py`/`build_main_class_dataset.py` defines them, plus `side_jaccard`
# (a sibling field on every row of `main_class_pooled_1100.jsonl`, not one of the 35, per the
# corrected Task 8 brief) as a 36th input feature.
DECISION_FEATURE_COLUMNS = [
    "turn", "turnActionCount", "energyAttached", "supporterPlayed", "stadiumPlayed", "retreated",
    "you_active_hp", "you_bench_count", "you_hand_count", "you_discard_count", "you_deck_count",
    "you_prize_count", "opp_active_hp", "opp_bench_count", "opp_hand_count", "opp_discard_count",
    "opp_deck_count", "opp_prize_count", "select_type", "select_context", "select_minCount",
    "select_maxCount", "actor_score_norm", "opp_score_norm",
    "n_options", "n_play", "n_attach", "n_evolve", "n_ability", "n_retreat", "n_attack", "n_end",
    "max_attack_damage", "any_lethal", "best_attack_kills_active",
]
FEATURE_COLUMNS = DECISION_FEATURE_COLUMNS + ["side_jaccard"]

SCORE_FLOOR = 1100.0


def load_rows(path) -> list:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _row_to_feature_dict(row: dict) -> dict:
    feats = dict(row["features"])
    feats["side_jaccard"] = row.get("side_jaccard") if row.get("side_jaccard") is not None else 0.0
    return feats


def build_frame(rows: list):
    """rows -> (X, y, groups, weights) as parallel structures, X a DataFrame in FEATURE_COLUMNS order."""
    X = pd.DataFrame([_row_to_feature_dict(r) for r in rows], columns=FEATURE_COLUMNS)
    y = [r["label"] for r in rows]
    groups = [r["episode_id"] for r in rows]
    weights = [r["weight"] for r in rows]
    return X, y, groups, weights


def train(rows: list, holdout_cluster=None) -> dict:
    """Train the class-prior model.

    `holdout_cluster`: optional set/frozenset of `episode_id`s to exclude ENTIRELY from training
    (every row belonging to any of those episodes is dropped before fitting) -- this is how G3b's
    "retrain holding out one whole deck cluster" is implemented: the caller passes the full set of
    episode_ids touched by the target cluster (both "pure" episodes and any "mixed" episode where
    a qualifying opposing side also happened to be in that cluster), so no cluster-cluster leakage
    survives into the fitted model.

    When `holdout_cluster` is None (G3a's call), an internal `GroupShuffleSplit` (grouped on
    `episode_id`, test_size=0.2, random_state=0, mirroring `train_intent_classifier.py`) reserves
    a random 20% of episodes for the returned bundle's own `test_rows`; the model is fit on the
    other 80% only, matching this repo's existing convention of shipping the split-fit model
    rather than a model refit on 100% of the data.

    When `holdout_cluster` is given, there is no internal split -- the model is fit on ALL
    non-held-out rows, since the held-out cluster itself is the intended test set (the caller
    evaluates it separately via `report`).
    """
    if holdout_cluster:
        holdout_cluster = set(holdout_cluster)
        use_rows = [r for r in rows if r["episode_id"] not in holdout_cluster]
    else:
        use_rows = rows

    X, y, groups, weights = build_frame(use_rows)

    if holdout_cluster:
        train_idx = list(range(len(use_rows)))
        test_rows = []
    else:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)
        train_idx, test_idx = next(splitter.split(X, y, groups))
        test_rows = [use_rows[i] for i in test_idx]

    model = HistGradientBoostingClassifier(
        max_iter=300, max_depth=6, learning_rate=0.08,
        class_weight="balanced", random_state=0,
    )
    model.fit(X.iloc[train_idx], [y[i] for i in train_idx],
              sample_weight=[weights[i] for i in train_idx])

    return {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "classes": sorted(model.classes_),
        "test_rows": test_rows,
        "holdout_cluster": holdout_cluster,
        "n_train": len(train_idx),
    }


def availability_baseline(rows: list) -> float:
    """Accuracy of always predicting "the most common class among the currently-legal ones",
    computed per-decision (grouped by that decision's `avail` set) -- NOT a single global
    majority class, since different decisions have different legal option-type sets. Evaluated
    directly on `rows` (majority computed from the same rows being scored), mirroring
    `train_intent_classifier.py`'s own majority-baseline-on-the-test-set pattern.
    """
    if not rows:
        return 0.0
    groups = defaultdict(Counter)
    for r in rows:
        avail_key = tuple(sorted(r["avail"]))
        groups[avail_key][r["label"]] += 1
    majority = {k: c.most_common(1)[0][0] for k, c in groups.items()}
    correct = sum(1 for r in rows if r["label"] == majority[tuple(sorted(r["avail"]))])
    return correct / len(rows)


def _masked_argmax(proba_row, classes, avail) -> int:
    """argmax restricted to classes legal in this decision (`avail`)."""
    avail_set = set(avail)
    best_c, best_p = None, -1.0
    for c, p in zip(classes, proba_row):
        if c in avail_set and p > best_p:
            best_c, best_p = c, p
    if best_c is None:
        # Defensive fallback only -- every row's own label is always in its own avail set by
        # construction, so this only fires if none of the model's *known* classes are legal here.
        best_c = sorted(avail)[0]
    return best_c


def report(bundle: dict, test_rows: list) -> dict:
    """Masked top-1 accuracy of `bundle`'s model on `test_rows`, vs `availability_baseline`."""
    if not test_rows:
        return {"n": 0, "masked_top1_accuracy": 0.0, "availability_baseline": 0.0, "lift_pp": 0.0}
    model = bundle["model"]
    classes = list(model.classes_)
    X, y, _, _ = build_frame(test_rows)
    proba = model.predict_proba(X)
    preds = [_masked_argmax(proba[i], classes, test_rows[i]["avail"]) for i in range(len(test_rows))]
    correct = sum(1 for p, r in zip(preds, test_rows) if p == r["label"])
    acc = correct / len(test_rows)
    baseline = availability_baseline(test_rows)
    return {
        "n": len(test_rows),
        "masked_top1_accuracy": acc,
        "availability_baseline": baseline,
        "lift_pp": (acc - baseline) * 100.0,
    }


# ---------------------------------------------------------------------------
# G3b support: mine deck clusters from the same floor-1100 population used to build the pooled
# dataset, and assign the resulting cluster ids back onto `episode_id`s.
# ---------------------------------------------------------------------------

def _qualifying_sides(records_path, score_floor: float = SCORE_FLOOR) -> dict:
    """(episode_id, player) -> {"actor_deck", "actor_team"} for every side that passes the same
    Orbit Wars rating gate `build_main_class_dataset.iter_main_decisions` used to build
    `main_class_pooled_1100.jsonl` (`score_floor=1100`, `require_win_or_strong_opp=True`) -- i.e.
    exactly the side population underlying that file. Streams the 3.0 GB raw corpus once.
    """
    sides = {}
    with open(records_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (rec.get("episode_id"), rec.get("player"))
            if key in sides:
                continue
            deck = rec.get("actor_deck")
            if not deck:
                continue
            passes = _passes_rating(rec.get("actor_score"), rec.get("opp_score"),
                                     rec.get("actor_reward"), score_floor, True)
            if not passes:
                continue
            sides[key] = {"actor_deck": deck, "actor_team": rec.get("actor_team")}
    return sides


def _assign_clusters(sides: dict, threshold: float = 0.7):
    """Greedy single-pass clustering identical to `deck_meta.cluster_decks`'s algorithm (reuses
    `deck_meta.jaccard` for every comparison), but also returns the per-side cluster assignment
    that `cluster_decks` itself doesn't expose -- needed to know which `episode_id`s a given
    cluster touches.

    Returns (`clusters`: list of {"counter", "keys": [(episode_id, player), ...]},
             `assignment`: {(episode_id, player) -> cluster_index}).
    """
    clusters = []  # each: {"counter": Counter, "keys": [...]}
    assignment = {}
    for key, side in sides.items():
        counter = Counter(side["actor_deck"])
        best, best_sim = None, 0.0
        for ci, c in enumerate(clusters):
            sim = deck_meta.jaccard(counter, c["counter"])
            if sim > best_sim:
                best, best_sim = ci, sim
        if best is not None and best_sim >= threshold:
            clusters[best]["keys"].append(key)
            assignment[key] = best
        else:
            clusters.append({"counter": counter, "keys": [key]})
            assignment[key] = len(clusters) - 1
    return clusters, assignment


def pick_holdout_cluster(records_path, deck_ref_path, rank: int = 1, threshold: float = 0.7):
    """Mine deck clusters at floor 1100 and pick the cluster at size-rank `rank` (0 = largest) as
    the G3b held-out cluster.

    Default `rank=1` (second-largest, not the largest) deliberately keeps the single biggest
    cluster in the training pool as an anchor, so the remaining training set stays well-populated
    and multi-cluster -- this is meant to be the FRIENDLIEST possible transfer test (a shift
    between two large, well-represented clusters), per the brief's own framing: if the class prior
    cannot survive even that shift, it will certainly not survive the harsher ~0.35-Jaccard gap to
    our actual deck.

    Returns (holdout_episode_ids: set -- ALL episodes touched by the held-out cluster, for
    excluding from training; pure_test_episode_ids: set -- only episodes where every qualifying
    side is the held-out cluster, safe to use as an unambiguous test set; cluster_info: dict of
    diagnostics for the report).
    """
    sides = _qualifying_sides(records_path)
    clusters, assignment = _assign_clusters(sides, threshold=threshold)
    deck_ref = deck_meta.load_deck_csv(Path(deck_ref_path))
    deck_ref_counter = Counter(deck_ref)

    order = sorted(range(len(clusters)), key=lambda i: len(clusters[i]["keys"]), reverse=True)
    if rank >= len(order):
        raise ValueError(f"rank {rank} out of range, only {len(order)} clusters")
    target_ci = order[rank]

    by_episode = defaultdict(list)
    for key in sides:
        by_episode[key[0]].append(key)

    touched_episodes = {k[0] for k in clusters[target_ci]["keys"]}
    pure_episodes = {
        eid for eid in touched_episodes
        if {assignment[k] for k in by_episode[eid]} == {target_ci}
    }

    cluster_info = {
        "rank": rank,
        "cluster_index": target_ci,
        "n_clusters_total": len(clusters),
        "n_sides": len(clusters[target_ci]["keys"]),
        "n_episodes_touched": len(touched_episodes),
        "n_episodes_pure": len(pure_episodes),
        "jaccard_vs_crustle_ref": deck_meta.jaccard(clusters[target_ci]["counter"], deck_ref_counter),
        "largest_cluster_sides": len(clusters[order[0]]["keys"]),
    }
    return touched_episodes, pure_episodes, cluster_info


# ---------------------------------------------------------------------------
# G3c support: replay Task 3's harvested Crustle self-play states through the trained model.
# ---------------------------------------------------------------------------

def iter_replay_decisions(shards_glob: str = DEFAULT_SELFPLAY_GLOB, min_options: int = 2):
    """Yield `{"features", "label", "avail"}` for every MAIN-eligible decision in the Task 3
    replayed Crustle shards, reusing `build_main_class_dataset`'s own eligibility filter and
    `decision_features` (not reimplemented) -- confirmed to reproduce Task 3's own audit exactly:
    79,041 eligible out of 122,414 examined, matching
    `data/processed/instrumentation/crustle_main_audit.json`'s `stats.examined`/`stats.eligible`.

    These states carry no `actor_deck` (they are Crustle's own harvested self-play, not a
    cross-deck corpus) and no ladder `actor_score`/`opp_score` join, so `side_jaccard` is set to
    1.0 for every row (a Crustle state's jaccard to the Crustle reference deck is definitionally
    1.0) and no rating gate is applied.
    """
    for path in sorted(glob.glob(shards_glob)):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                select = rec.get("select") or {}
                action = rec.get("action") or []
                if not _is_eligible_record(select, action, min_options):
                    continue
                options = select.get("option") or []
                label = options[action[0]].get("type")
                avail = sorted({o.get("type") for o in options})
                feats = decision_features(select, rec.get("current") or {},
                                           rec.get("actor_score"), rec.get("opp_score"))
                feats["side_jaccard"] = 1.0
                yield {"features": feats, "label": label, "avail": avail}


def disagreement_rate(bundle: dict, replay_rows: list) -> dict:
    model = bundle["model"]
    classes = list(model.classes_)
    X = pd.DataFrame([r["features"] for r in replay_rows], columns=FEATURE_COLUMNS)
    proba = model.predict_proba(X)
    preds = [_masked_argmax(proba[i], classes, replay_rows[i]["avail"]) for i in range(len(replay_rows))]
    disagree = sum(1 for p, r in zip(preds, replay_rows) if p != r["label"])
    return {"n": len(replay_rows), "disagree": disagree, "disagreement_rate": disagree / len(replay_rows)}


# ---------------------------------------------------------------------------
# Driver: run all three gates and print the report.
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default=str(DEFAULT_RECORDS))
    ap.add_argument("--raw-corpus", default=str(DEFAULT_RAW_CORPUS))
    ap.add_argument("--selfplay-glob", default=DEFAULT_SELFPLAY_GLOB)
    ap.add_argument("--deck-ref", default=str(DEFAULT_DECK_REF))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--holdout-rank", type=int, default=1,
                     help="Deck-cluster size rank to hold out for G3b (0=largest, default 1=2nd largest).")
    args = ap.parse_args()

    t0 = time.time()
    print(f"loading {args.records} ...")
    rows = load_rows(args.records)
    print(f"  {len(rows)} rows, {len(set(r['episode_id'] for r in rows))} episodes")

    # ---------------- G3a: informativeness ----------------
    print("\n=== G3a: informativeness ===")
    bundle_full = train(rows, holdout_cluster=None)
    g3a = report(bundle_full, bundle_full["test_rows"])
    g3a_pass = g3a["lift_pp"] >= 5.0
    print(f"  masked top-1 accuracy: {g3a['masked_top1_accuracy']:.1%}")
    print(f"  availability_baseline: {g3a['availability_baseline']:.1%}")
    print(f"  lift: {g3a['lift_pp']:.2f}pp (need >= 5.0pp)  -> {'PASS' if g3a_pass else 'FAIL'}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": bundle_full["model"], "feature_columns": FEATURE_COLUMNS,
                 "classes": bundle_full["classes"]}, out_path)
    print(f"  wrote {out_path}")

    # ---------------- G3b: transfer ----------------
    print("\n=== G3b: transfer ===")
    holdout_eps, pure_eps, cluster_info = pick_holdout_cluster(
        args.raw_corpus, args.deck_ref, rank=args.holdout_rank)
    print(f"  held-out cluster: rank {cluster_info['rank']} of {cluster_info['n_clusters_total']}, "
          f"{cluster_info['n_sides']} sides, {cluster_info['n_episodes_touched']} episodes touched "
          f"({cluster_info['n_episodes_pure']} pure), jaccard_vs_crustle="
          f"{cluster_info['jaccard_vs_crustle_ref']:.3f} "
          f"(largest cluster has {cluster_info['largest_cluster_sides']} sides, stays in training)")

    bundle_holdout = train(rows, holdout_cluster=holdout_eps)
    pure_test_rows = [r for r in rows if r["episode_id"] in pure_eps]
    print(f"  trained on {bundle_holdout['n_train']} rows "
          f"(excluded {len(rows) - bundle_holdout['n_train']} rows in {len(holdout_eps)} touched episodes)")
    print(f"  held-out cluster test set: {len(pure_test_rows)} rows ({len(pure_eps)} pure episodes)")

    g3b_raw = report(bundle_holdout, pure_test_rows)
    retention = (g3b_raw["lift_pp"] / g3a["lift_pp"]) if g3a["lift_pp"] else 0.0
    g3b_pass = retention >= 0.60
    print(f"  masked top-1 accuracy on held-out cluster: {g3b_raw['masked_top1_accuracy']:.1%}")
    print(f"  availability_baseline on held-out cluster: {g3b_raw['availability_baseline']:.1%}")
    print(f"  held-out lift: {g3b_raw['lift_pp']:.2f}pp / in-distribution lift: {g3a['lift_pp']:.2f}pp")
    print(f"  retention: {retention:.1%} (need >= 60%)  -> {'PASS' if g3b_pass else 'FAIL'}")

    # ---------------- G3c: disagreement ----------------
    print("\n=== G3c: disagreement ===")
    replay_rows = list(iter_replay_decisions(args.selfplay_glob))
    g3c = disagreement_rate(bundle_full, replay_rows)
    g3c_pass = 0.08 <= g3c["disagreement_rate"] <= 0.35
    print(f"  {g3c['n']} replayed MAIN-eligible decisions, {g3c['disagree']} disagreements")
    print(f"  disagreement rate: {g3c['disagreement_rate']:.1%} (need 8-35%)  -> "
          f"{'PASS' if g3c_pass else 'FAIL'}")

    overall_pass = g3a_pass and g3b_pass and g3c_pass
    print(f"\n=== OVERALL: {'PASS' if overall_pass else 'FAIL'} "
          f"({time.time() - t0:.0f}s elapsed) ===")

    result = {
        "g3a": {**g3a, "pass": g3a_pass},
        "g3b": {**g3b_raw, "retention": retention, "pass": g3b_pass, "cluster_info": cluster_info},
        "g3c": {**g3c, "pass": g3c_pass},
        "overall_pass": overall_pass,
    }
    print(json.dumps(result, indent=2, default=str))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
