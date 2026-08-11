"""Bit-for-bit verification: pure_predictor's multiclass inference vs sklearn's own.

Run: python3 src/test_pure_predictor_multiclass.py

Required by CLAUDE.md before this predictor is usable by Task 14b: the first IL submission
ERRORed on the real Kaggle sandbox despite running fine locally, so any stdlib re-implementation
of sklearn inference must be verified against sklearn's own predict_proba before it ships, not
just assumed correct because it "looks right".

Skips cleanly (not fail) if the model/export artifacts don't exist yet — they're gitignored
build products (models/), not something this test file's presence should require.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pure_predictor  # noqa: E402
from train_intent_classifier import FEATURE_COLUMNS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_PKL = REPO_ROOT / "models" / "il_intent_classifier.pkl"
MODEL_JSON = REPO_ROOT / "models" / "il_intent_classifier_pure.json"
RECORDS = REPO_ROOT / "data" / "processed" / "il_intent_turns.jsonl"

FAILURES = []
SKIPPED = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


def skip(name: str, why: str):
    print(f"  skip  {name}   ({why})")
    SKIPPED.append(name)


def load_sample_rows(n=100):
    rows = []
    with open(RECORDS) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:n] if len(rows) > n else rows


def main():
    if not MODEL_PKL.exists() or not MODEL_JSON.exists():
        skip("bit-for-bit multiclass verification",
             f"missing {MODEL_PKL.name if not MODEL_PKL.exists() else MODEL_JSON.name}")
        return

    import joblib  # only needed to load the sklearn model for comparison, never at inference time

    # Safe: loading our own model artifact, produced earlier in this same pipeline run — not an
    # untrusted source (see export_pure_predictor.py's identical justification).
    bundle_sklearn = joblib.load(MODEL_PKL)
    model = bundle_sklearn["model"]
    bundle_json = pure_predictor.load(str(MODEL_JSON))

    check("exported mode is multiclass", bundle_json.get("mode") == "multiclass",
          f"got {bundle_json.get('mode')!r}")
    check("exported classes match model.classes_ exactly (order included)",
          bundle_json["classes"] == [str(c) for c in model.classes_],
          f"{bundle_json['classes']} vs {list(model.classes_)}")
    check("exported feature_columns match training's FEATURE_COLUMNS",
          bundle_json["feature_columns"] == FEATURE_COLUMNS,
          f"{bundle_json['feature_columns']} vs {FEATURE_COLUMNS}")

    rows = load_sample_rows(100)
    check("at least one row available for comparison", len(rows) > 0,
          f"{RECORDS} is empty")
    if not rows:
        return

    import pandas as pd
    feature_rows = [[r["features"][c] for c in FEATURE_COLUMNS] for r in rows]
    X = pd.DataFrame([r["features"] for r in rows], columns=FEATURE_COLUMNS)
    sklearn_proba = model.predict_proba(X)

    max_abs_diff = 0.0
    mismatches = 0
    for i, feature_row in enumerate(feature_rows):
        pure_proba = pure_predictor.predict_multiclass_one(bundle_json, feature_row)
        sk_proba = sklearn_proba[i].tolist()
        if len(pure_proba) != len(sk_proba):
            mismatches += 1
            continue
        diffs = [abs(a - b) for a, b in zip(pure_proba, sk_proba)]
        max_abs_diff = max(max_abs_diff, max(diffs))
        if max(diffs) > 1e-9:
            mismatches += 1

    check(f"predict_multiclass_one matches sklearn predict_proba within 1e-9 "
          f"across {len(feature_rows)} rows",
          mismatches == 0, f"{mismatches} rows mismatched, max abs diff {max_abs_diff:.3e}")

    # predict_one must dispatch to the multiclass path identically for this bundle.
    dispatch_ok = all(
        pure_predictor.predict_one(bundle_json, fr) == pure_predictor.predict_multiclass_one(bundle_json, fr)
        for fr in feature_rows
    )
    check("predict_one dispatches multiclass bundles to predict_multiclass_one", dispatch_ok)

    print()
    print(f"        compared {len(feature_rows)} rows, max abs diff {max_abs_diff:.3e}")


if __name__ == "__main__":
    main()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print(f"all passed ({len(SKIPPED)} skipped)")
