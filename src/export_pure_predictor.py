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

    trees = []
    for stage in model._predictors:
        tree = stage[0]  # binary classification: one tree per boosting iteration
        nodes = []
        for node in tree.nodes:
            nodes.append(
                [
                    int(node["feature_idx"]),
                    float(node["num_threshold"]),
                    int(node["missing_go_to_left"]),
                    int(node["left"]),
                    int(node["right"]),
                    int(node["is_leaf"]),
                    float(node["value"]),
                ]
            )
        trees.append(nodes)

    baseline = float(model._baseline_prediction.reshape(-1)[0])

    payload = {
        "feature_columns": feature_columns,
        "baseline": baseline,
        "trees": trees,
        "threshold": threshold,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f)
    print(f"exported {len(trees)} trees, {sum(len(t) for t in trees)} nodes, threshold={threshold} -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="models/il_scorer_v2.pkl")
    parser.add_argument("--out", default="models/il_scorer_v2_pure.json")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    export_model(args.model, args.out, args.threshold)
