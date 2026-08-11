"""Export a trained HistGradientBoostingClassifier into a pure stdlib-only format.

Why: the first IL submission (ERROR on Kaggle, ran fine locally and on the extracted tar)
strongly suggests the competition's simulation sandbox does not include numpy/pandas/
scikit-learn/joblib the way an interactive Kaggle notebook does — every other submission here
uses only stdlib + the competition's own compiled cg engine, and this was the first to pull in
the data-science stack. Rather than gamble on package availability, export the model's actual
decision-tree structure (still a HistGradientBoostingClassifier — same accuracy) into plain
JSON and write a companion predictor that needs nothing beyond `json` and `math` from stdlib.

Usage:
    python src/export_pure_predictor.py --model models/il_scorer_v2.pkl --out models/il_scorer_v2_pure.json
"""

import argparse
import json


def export_model(model_path: str, out_path: str, threshold: float = 0.5):
    import joblib  # only needed for this export step, never at inference time

    # Safe: loading our own model artifact, trained locally in this session — not an
    # untrusted source. This export step only ever runs on our own machine, never in the
    # Kaggle sandbox (that's the whole point — the exported JSON is what ships instead).
    bundle = joblib.load(model_path)
    model = bundle["model"]
    feature_columns = bundle["feature_columns"]

    def dump_tree(tree):
        nodes = []
        for node in tree.nodes:
            nodes.append([
                int(node["feature_idx"]), float(node["num_threshold"]),
                int(node["missing_go_to_left"]), int(node["left"]), int(node["right"]),
                int(node["is_leaf"]), float(node["value"]),
            ])
        return nodes

    n_trees_per_iter = len(model._predictors[0])
    baseline_arr = model._baseline_prediction.reshape(-1)

    if n_trees_per_iter == 1:
        # Binary classification: unchanged from the original export, plus an explicit mode tag.
        trees = [dump_tree(stage[0]) for stage in model._predictors]
        payload = {
            "mode": "binary",
            "feature_columns": feature_columns,
            "baseline": float(baseline_arr[0]),
            "trees": trees,
            "threshold": threshold,
        }
        print(f"exported {len(trees)} trees, {sum(len(t) for t in trees)} nodes, "
              f"mode=binary, threshold={threshold} -> {out_path}")
    else:
        # Export the classes in model.classes_'s actual order (sklearn sorts alphabetically by
        # default), NOT bundle["classes"]'s order (train_intent_classifier.py's CLASSES constant
        # is base/aggro/develop/snipe/survive — not alphabetical) — predict_multiclass_one must
        # return probabilities in the same order model.predict_proba does, or the bit-for-bit
        # verification in test_pure_predictor_multiclass.py cannot pass.
        classes = [str(c) for c in model.classes_]
        trees_per_class = [[] for _ in range(n_trees_per_iter)]
        for stage in model._predictors:
            for k in range(n_trees_per_iter):
                trees_per_class[k].append(dump_tree(stage[k]))
        payload = {
            "mode": "multiclass",
            "feature_columns": feature_columns,
            "classes": classes,
            "baseline": [float(b) for b in baseline_arr],
            "trees_per_class": trees_per_class,
            "threshold": threshold,
        }
        total_nodes = sum(len(t) for trees in trees_per_class for t in trees)
        print(f"exported {n_trees_per_iter} classes x {len(trees_per_class[0])} trees "
              f"({total_nodes} nodes), mode=multiclass -> {out_path}")

    with open(out_path, "w") as f:
        json.dump(payload, f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="models/il_scorer_v2.pkl")
    parser.add_argument("--out", default="models/il_scorer_v2_pure.json")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    export_model(args.model, args.out, args.threshold)
