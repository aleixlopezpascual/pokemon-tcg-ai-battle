import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_main_decisions as aud

FAILURES = []
STATES = "data/processed/selfplay_crustle/shard_*.jsonl"

def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} {detail}")

def skip(name, why):
    print(f"SKIP {name} ({why})")

def main():
    if not list(Path(".").glob(STATES)):
        skip("all", "no dumped states; run ladder_eval rate --dump-states first")
        return
    decs = list(aud.replay_decisions(
        Path("submissions/soutasakurai_libraryout_crustle"), STATES, limit=2000))
    check("decisions found", len(decs) > 200, f"got {len(decs)}")

    hist = aud.margin_histogram(decs)
    check("histogram totals", sum(hist.values()) == len(decs),
          f"{sum(hist.values())} vs {len(decs)}")

    ties = aud.tie_report(decs)
    check("tie multiplicity totals", sum(ties["multiplicity"].values()) == len(decs))
    check("every decision has >=1 top option", min(ties["multiplicity"]) >= 1)

    mix = aud.class_mix(decs)
    check("class shares sum to 1", abs(sum(mix["chosen"].values()) - 1.0) < 1e-6)
    check("no DISCARD chosen", mix["chosen"].get(11, 0.0) == 0.0)
    check("chosen class always available",
          all(d["chosen_class"] in d["avail"] for d in decs))

if __name__ == "__main__":
    main()
    sys.exit(1 if FAILURES else 0)
