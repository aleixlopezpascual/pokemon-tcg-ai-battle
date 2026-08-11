"""Pure stdlib (json + math only) re-implementation of HistGradientBoostingClassifier inference.

No numpy, no scikit-learn, no joblib — see export_pure_predictor.py for why. Loads the JSON
produced by that script and reproduces sklearn's raw decision function (sum of tree outputs +
baseline) then applies the logistic sigmoid, matching `predict_proba(X)[:, 1]` for binary
classification.
"""

import json
import math


def load(json_path: str) -> dict:
    with open(json_path) as f:
        return json.load(f)


def _tree_predict(tree: list, features: list) -> float:
    node_idx = 0
    while True:
        feature_idx, threshold, missing_go_to_left, left, right, is_leaf, value = tree[node_idx]
        if is_leaf:
            return value
        x = features[feature_idx]
        if x is None:
            go_left = bool(missing_go_to_left)
        else:
            go_left = x <= threshold
        node_idx = left if go_left else right


def predict_proba_one(bundle: dict, feature_row: list) -> float:
    """feature_row must be ordered exactly as bundle['feature_columns']."""
    raw = bundle["baseline"]
    for tree in bundle["trees"]:
        raw += _tree_predict(tree, feature_row)
    return 1.0 / (1.0 + math.exp(-raw))


def predict_proba_batch(bundle: dict, feature_rows: list) -> list:
    return [predict_proba_one(bundle, row) for row in feature_rows]


def predict_multiclass_one(bundle: dict, feature_row: list) -> list:
    """Returns class probabilities in the order of bundle['classes']. mode must be 'multiclass'."""
    raw = list(bundle["baseline"])
    for k, trees in enumerate(bundle["trees_per_class"]):
        for tree in trees:
            raw[k] += _tree_predict(tree, feature_row)
    m = max(raw)
    exps = [math.exp(r - m) for r in raw]
    total = sum(exps)
    return [e / total for e in exps]


def predict_one(bundle: dict, feature_row: list):
    """Dispatch on bundle['mode']. Absent mode (older exports) is treated as binary."""
    if bundle.get("mode") == "multiclass":
        return predict_multiclass_one(bundle, feature_row)
    return predict_proba_one(bundle, feature_row)
