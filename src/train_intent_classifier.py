"""Train the 5-class intent classifier on labeled turns from src/label_intent_turns.py.

Usage:
    python3 src/train_intent_classifier.py \\
        --records data/processed/il_intent_turns.jsonl \\
        --out models/il_intent_classifier.pkl
"""

import argparse
import json

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupShuffleSplit

FEATURE_COLUMNS = [
    "turn", "turnActionCount", "energyAttached", "supporterPlayed", "stadiumPlayed", "retreated",
    "you_active_hp", "you_bench_count", "you_hand_count", "you_discard_count", "you_deck_count",
    "you_prize_count", "opp_active_hp", "opp_bench_count", "opp_hand_count", "opp_discard_count",
    "opp_deck_count", "opp_prize_count", "select_type", "select_context", "select_minCount",
    "select_maxCount", "actor_score_norm", "opp_score_norm",
]
CLASSES = ["base", "aggro", "develop", "snipe", "survive"]


def load_rows(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default="data/processed/il_intent_turns.jsonl")
    ap.add_argument("--out", default="models/il_intent_classifier.pkl")
    ap.add_argument("--test-size", type=float, default=0.2)
    args = ap.parse_args()

    rows = load_rows(args.records)
    X = pd.DataFrame([r["features"] for r in rows], columns=FEATURE_COLUMNS)
    y = [r["intent"] for r in rows]
    groups = [r["episode_id"] for r in rows]
    weights = [r["weight"] for r in rows]

    splitter = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=0)
    train_idx, test_idx = next(splitter.split(X, y, groups))

    model = HistGradientBoostingClassifier(
        max_iter=300, max_depth=6, learning_rate=0.08,
        class_weight="balanced", random_state=0,
    )
    model.fit(X.iloc[train_idx], [y[i] for i in train_idx],
              sample_weight=[weights[i] for i in train_idx])

    y_test = [y[i] for i in test_idx]
    y_pred = model.predict(X.iloc[test_idx])
    acc = accuracy_score(y_test, y_pred)

    from collections import Counter
    majority_class, majority_count = Counter(y_test).most_common(1)[0]
    majority_baseline = majority_count / len(y_test)

    print(f"held-out per-turn top-1 accuracy: {acc:.1%}")
    print(f"majority-class baseline ({majority_class}): {majority_baseline:.1%}")
    print(f"model classes_: {list(model.classes_)}")

    joblib.dump({"model": model, "feature_columns": FEATURE_COLUMNS, "classes": CLASSES},
                args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
