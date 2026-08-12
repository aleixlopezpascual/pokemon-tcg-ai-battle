import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mirror_eval

FAILURES = []

def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} {detail}")

def test_self_mirror_is_a_coinflip():
    base = Path("submissions/soutasakurai_libraryout_crustle")
    r = mirror_eval.mirror(base, base, games=2000, workers=8)
    check("self-mirror n", r["games"] == 2000, f"got {r['games']}")
    check("self-mirror CI contains 0.50",
          r["lo"] <= 0.50 <= r["hi"], f"wr={r['wr']:.4f} CI=[{r['lo']:.4f},{r['hi']:.4f}]")

if __name__ == "__main__":
    test_self_mirror_is_a_coinflip()
    sys.exit(1 if FAILURES else 0)
