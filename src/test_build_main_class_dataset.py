import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_main_class_dataset as bmc

FAILURES = []
RECORDS = Path("data/processed/il_records_v3_combined.jsonl")


def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} {detail}")


def main():
    if not RECORDS.exists():
        print("SKIP all (corpus absent)")
        return
    rows = []
    for i, r in enumerate(bmc.iter_main_decisions(RECORDS, score_floor=0.0,
                                                  require_win_or_strong_opp=False)):
        rows.append(r)
        if i >= 20000:
            break
    check("rows produced", len(rows) > 5000, f"got {len(rows)}")
    check("no DISCARD label", all(r["label"] != 11 for r in rows))
    check("label always available", all(r["label"] in r["avail"] for r in rows))
    check("END always legal", all(r["features"]["n_end"] >= 1 for r in rows))
    check("35 feature columns", all(len(r["features"]) == 35 for r in rows))
    check("weights positive", all(r["weight"] > 0 for r in rows))


if __name__ == "__main__":
    main()
    sys.exit(1 if FAILURES else 0)
