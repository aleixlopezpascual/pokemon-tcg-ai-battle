"""Sweep the option-selection probability threshold on a held-out split, optimizing for
decision-level exact-set-match (predicted chosen set == actual chosen set) rather than top-1 —
this is what actually determines in-game behavior (main.py clips a thresholded set to
[minCount, maxCount], not just an argmax).

Usage:
    python src/calibrate_threshold.py --model models/il_scorer_v3.pkl --records data/processed/il_records_v3_combined.jsonl --out models/il_scorer_v3_threshold.txt
"""

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import build_dataset  # noqa: E402


def exact_match_rate(model, X, decision_ids, y, select_min_max, threshold):
    scores = model.predict_proba(X)[:, 1]
    correct, total = 0, 0
    for dec_id in np.unique(decision_ids):
        mask = decision_ids == dec_id
        dec_scores = scores[mask]
        dec_labels = y[mask]
        min_c, max_c = select_min_max[dec_id]
        ranked = np.argsort(-dec_scores)
        above = [i for i in ranked if dec_scores[i] > threshold]
        if len(above) < min_c:
            chosen = set(ranked[:min_c])
        elif len(above) > max_c:
            chosen = set(ranked[:max_c])
        else:
            chosen = set(above)
        actual = set(np.where(dec_labels == 1)[0])
        total += 1
        if chosen == actual:
            correct += 1
    return correct / total if total else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--records", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    # Safe: loading our own model artifact, trained locally by src/train_il_model.py in this
    # same pipeline — not an untrusted source. Same pattern already used in
    # src/export_pure_predictor.py. This script only ever runs on our own machine, never in the
    # Kaggle sandbox — the exported pure-JSON bundle (Task 7 Step 3-4) is what actually ships.
    bundle = joblib.load(args.model)
    model, feature_columns = bundle["model"], bundle["feature_columns"]

    rows, labels, decision_ids, _weights, episode_ids = build_dataset(args.records)
    X = pd.DataFrame(rows)[feature_columns]
    y = np.array(labels)
    groups = np.array(decision_ids)
    split_groups = np.array(episode_ids)

    # Recover per-decision minCount/maxCount for the exact-set-match check.
    select_min_max = {}
    for row, dec_id in zip(rows, decision_ids):
        if dec_id not in select_min_max:
            select_min_max[dec_id] = (row["select_minCount"], row["select_maxCount"])

    # Split on episode_ids (not decision_ids) to reproduce the exact same held-out set that
    # src/train_il_model.py trained against — same GroupShuffleSplit params (test_size=0.2,
    # random_state=0) it uses, keyed by the same grouping. Splitting on decision_ids instead
    # would recover a *different* (leakier) test set than the model was actually evaluated on.
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)
    _, test_idx = next(splitter.split(X, y, split_groups))
    X_test, y_test, groups_test = X.iloc[test_idx], y[test_idx], groups[test_idx]

    best_threshold, best_rate = 0.5, -1.0
    for threshold in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]:
        rate = exact_match_rate(model, X_test, groups_test, y_test, select_min_max, threshold)
        print(f"threshold {threshold:.2f}: exact-set-match {rate:.3f}")
        if rate > best_rate:
            best_threshold, best_rate = threshold, rate

    print(f"best threshold: {best_threshold} (exact-set-match {best_rate:.3f})")
    Path(args.out).write_text(str(best_threshold))


if __name__ == "__main__":
    main()
