"""Train a scorer-over-legal-options model from parsed episode replay records.

Pointwise formulation: one row per (decision, option) pair, binary label "was this option
chosen." At inference, score every legal option for a decision and pick the argmax (or top-k
for maxCount>1) — the same shape every rule-based agent in this repo already uses, just with
learned weights instead of hand-tuned ones.

Evaluation metric that matters: per-decision top-1 accuracy (did the model's highest-scored
option match the option actually chosen), not row-level accuracy, which is dominated by the
easy true-negatives.

Usage:
    python src/train_il_model.py --records data/processed/il_records.jsonl --out models/il_scorer_v1.pkl
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import build_dataset  # noqa: E402


def per_decision_top1_accuracy(model, X: pd.DataFrame, decision_ids: np.ndarray, y: np.ndarray) -> float:
    scores = model.predict_proba(X)[:, 1]
    correct, total = 0, 0
    for dec_id in np.unique(decision_ids):
        mask = decision_ids == dec_id
        dec_scores = scores[mask]
        dec_labels = y[mask]
        if dec_labels.sum() == 0:
            continue  # shouldn't happen, but be defensive
        predicted_idx = np.argmax(dec_scores)
        actual_idx = np.argmax(dec_labels)  # first true label position (pointwise top-1 case)
        total += 1
        if predicted_idx == actual_idx and dec_labels[predicted_idx] == 1:
            correct += 1
    return correct / total if total else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--records", default="data/processed/il_records.jsonl")
    parser.add_argument("--out", default="models/il_scorer_v1.pkl")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--max-records", type=int, default=None,
                         help="Truncate to the first N raw JSONL lines, for fast iteration")
    args = parser.parse_args()

    print("building dataset...")
    rows, labels, decision_ids, weights = build_dataset(args.records, max_records=args.max_records)
    X = pd.DataFrame(rows)
    y = np.array(labels)
    groups = np.array(decision_ids)
    w = np.array(weights)
    print(f"{len(X)} rows, {len(np.unique(groups))} decisions, positive rate {y.mean():.3f}")

    splitter = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=0)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    w_train = w[train_idx]
    groups_test = groups[test_idx]

    print(f"train: {len(X_train)} rows / {len(np.unique(groups[train_idx]))} decisions, "
          f"test: {len(X_test)} rows / {len(np.unique(groups_test))} decisions")

    model = HistGradientBoostingClassifier(
        max_iter=300,
        max_depth=6,
        learning_rate=0.08,
        class_weight="balanced",
        random_state=0,
    )
    print("training...")
    model.fit(X_train, y_train, sample_weight=w_train)

    train_acc = per_decision_top1_accuracy(model, X_train, groups[train_idx], y_train)
    test_acc = per_decision_top1_accuracy(model, X_test, groups_test, y_test)
    print(f"per-decision top-1 accuracy — train: {train_acc:.3f}, test: {test_acc:.3f}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"model": model, "feature_columns": list(X.columns)}, out_path)
    print(f"saved model -> {out_path}")


if __name__ == "__main__":
    main()
