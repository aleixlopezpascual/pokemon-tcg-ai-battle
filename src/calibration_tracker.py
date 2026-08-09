"""Track how well local evaluation predicts the real ladder, and say honestly how well it doesn't.

The point of this file is the *comparison*: for every candidate whose submitted code still matches
a local directory, record both local metrics (frozen-panel TrueSkill mu from `ladder_eval.py`, and
pooled win rate as the incumbent baseline) alongside its settled ladder mu. Then rank-correlate
each against the ladder. If the frozen-panel swap was worth doing, its rho beats pooled WR's.

Why the previous calibration table in `baseline-comparison.md` could not answer this: its three
rows were measured against a 4-agent roster, later numbers against 5- and 7-agent rosters. Those
are different measuring sticks, so no correlation could legitimately be computed across them.
Here `panel_version` is a required column and rows from different panels are *excluded* from a
report rather than silently mixed.

Two hard limits, stated up front because the numbers look more authoritative than they are:

1. **n is tiny.** Only candidates we actually submitted, whose local code still matches what was
   submitted, are eligible. That is n=5 today. Exact permutation p-values are reported rather than
   an asymptotic approximation, because at n=5 the smallest attainable two-sided p is 2/120 =
   0.017 and only a *perfect* rank match reaches it. A high rho here is suggestive, not evidence.
2. **The target is itself noisy.** Ladder mu drifts between readings on identical code
   (`55327510` read 771.6 / 811.4 / 774.8). `settled_mu` is the latest reading with >=2 readings
   >=24h apart; `readings` keeps the whole history so the drift is visible.

Usage:
    python3 src/calibration_tracker.py record --candidate kiyota_dragapult_ex \
        --result-json data/processed/ratings/kiyota_dragapult_ex.json \
        --submission-ref 55336268 --readings 698.5
    python3 src/calibration_tracker.py report
"""

import argparse
import csv
import json
import math
import random
from itertools import permutations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CALIBRATION_PATH = REPO_ROOT / "data" / "processed" / "calibration.csv"

FIELDS = [
    "candidate", "panel_version", "local_mu", "local_sigma", "pooled_wr", "games",
    "submission_ref", "readings", "settled_mu", "measured_date", "notes",
]


# ---------------------------------------------------------------------------
# rank correlation (no scipy: keep this runnable from a bare interpreter, same
# as the rest of the evaluation stack)
# ---------------------------------------------------------------------------


def _ranks(xs: list) -> list:
    """Fractional ranks, ties averaged — the standard Spearman tie correction."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: list, ys: list) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def spearman(xs: list, ys: list) -> float:
    return _pearson(_ranks(xs), _ranks(ys))


def permutation_p(xs: list, ys: list, max_exact: int = 40320, iters: int = 200000) -> tuple:
    """Two-sided p for |rho| under the null that the pairing is arbitrary.

    Exact (enumerate every permutation of y) while n! is small enough — which it always is at the
    n this project will ever reach — otherwise Monte-Carlo. Returns (p, "exact"|"sampled").
    """
    n = len(xs)
    observed = abs(spearman(xs, ys))
    rx = _ranks(xs)
    fact = math.factorial(n)
    if fact <= max_exact:
        hits = sum(1 for perm in permutations(ys) if abs(_pearson(rx, _ranks(list(perm)))) >= observed - 1e-12)
        return hits / fact, "exact"
    rng = random.Random(0)
    shuffled = list(ys)
    hits = 0
    for _ in range(iters):
        rng.shuffle(shuffled)
        if abs(_pearson(rx, _ranks(shuffled))) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (iters + 1), "sampled"


def bootstrap_ci(xs: list, ys: list, iters: int = 20000, alpha: float = 0.05) -> tuple:
    """Percentile bootstrap over *pairs*. At small n this is wide by construction — that is the
    honest answer, not a defect to tune away."""
    rng = random.Random(0)
    n = len(xs)
    vals = []
    for _ in range(iters):
        idx = [rng.randrange(n) for _ in range(n)]
        bx = [xs[i] for i in idx]
        by = [ys[i] for i in idx]
        # A resample can be constant in x or y (all-same index draw); rho is undefined there.
        if len(set(bx)) < 2 or len(set(by)) < 2:
            continue
        vals.append(spearman(bx, by))
    if not vals:
        return (float("nan"), float("nan"))
    vals.sort()
    lo = vals[int(alpha / 2 * len(vals))]
    hi = vals[min(len(vals) - 1, int((1 - alpha / 2) * len(vals)))]
    return lo, hi


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


def load_rows() -> list:
    if not CALIBRATION_PATH.exists():
        return []
    with CALIBRATION_PATH.open() as f:
        return list(csv.DictReader(f))


def append_row(row: dict):
    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = CALIBRATION_PATH.exists()
    with CALIBRATION_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def cmd_record(args):
    row = {
        "candidate": args.candidate,
        "submission_ref": args.submission_ref or "",
        "measured_date": args.date,
        "notes": args.notes or "",
    }
    if args.result_json:
        res = json.loads(Path(args.result_json).read_text())
        row.update({
            "candidate": args.candidate or res["candidate"],
            "panel_version": res["panel_version"],
            "local_mu": f"{res['local_mu']:.2f}",
            "local_sigma": f"{res['local_sigma']:.2f}",
            "pooled_wr": f"{res['pooled_wr']:.4f}",
            "games": res["games"],
        })
    else:
        row.update({
            "panel_version": args.panel_version,
            "local_mu": args.local_mu, "local_sigma": args.local_sigma,
            "pooled_wr": args.pooled_wr, "games": args.games,
        })

    readings = [float(x) for x in (args.readings or [])]
    row["readings"] = ";".join(f"{r:g}" for r in readings)
    # Settled = the most recent reading, and only once there are at least two. A single reading is
    # recorded but deliberately left without a settled value so `report` skips it: same-agent
    # first readings here have landed 300+ points apart.
    row["settled_mu"] = f"{readings[-1]:.1f}" if len(readings) >= 2 else ""
    append_row(row)
    print(f"recorded {row['candidate']} (panel {row['panel_version']}) "
          f"local_mu={row['local_mu']} settled_mu={row['settled_mu'] or 'unsettled'}")


def _report_metric(name: str, locals_: list, ladder: list, note: str = ""):
    rho = spearman(locals_, ladder)
    lo, hi = bootstrap_ci(locals_, ladder)
    p, kind = permutation_p(locals_, ladder)
    print(f"  {name:<12} rho {rho:+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]   "
          f"p={p:.3f} ({kind})  {note}")
    return rho


def cmd_report(args):
    rows = load_rows()
    if not rows:
        raise SystemExit(f"no rows in {CALIBRATION_PATH}; run `record` first")

    versions = sorted({r["panel_version"] for r in rows if r["panel_version"]})
    target = args.panel_version or max(
        versions, key=lambda v: sum(1 for r in rows if r["panel_version"] == v))
    dropped = [r for r in rows if r["panel_version"] != target]

    usable = [r for r in rows if r["panel_version"] == target and r["settled_mu"]]
    unsettled = [r for r in rows if r["panel_version"] == target and not r["settled_mu"]]

    print(f"panel_version {target}")
    if dropped:
        print(f"  excluded {len(dropped)} row(s) from other panel versions "
              f"({sorted({r['panel_version'] for r in dropped})}) — different measuring stick, "
              f"not comparable")
    if unsettled:
        print(f"  excluded {len(unsettled)} row(s) without a settled ladder mu "
              f"({', '.join(r['candidate'] for r in unsettled)})")

    if len(usable) < 3:
        print(f"\n  only {len(usable)} usable row(s) — rank correlation is meaningless below 3. "
              f"Recording more requires more real submissions, not more local compute.")
        return

    usable.sort(key=lambda r: -float(r["settled_mu"]))
    print(f"\n{'candidate':<40} {'local mu':>9} {'pooled WR':>10} {'ladder mu':>10} {'ref':>10}")
    for r in usable:
        print(f"{r['candidate']:<40} {float(r['local_mu']):>9.1f} "
              f"{float(r['pooled_wr']) * 100:>9.1f}% {float(r['settled_mu']):>10.1f} "
              f"{r['submission_ref']:>10}")

    ladder = [float(r["settled_mu"]) for r in usable]
    mus = [float(r["local_mu"]) for r in usable]
    wrs = [float(r["pooled_wr"]) for r in usable]
    n = len(usable)

    print(f"\nrank correlation vs settled ladder mu (n={n})")
    rho_mu = _report_metric("local_mu", mus, ladder, "<- frozen-panel TrueSkill")
    rho_wr = _report_metric("pooled_wr", wrs, ladder, "<- incumbent, for comparison")

    print()
    if rho_mu > rho_wr:
        print(f"  frozen-panel mu ranks better than pooled WR (+{rho_mu - rho_wr:.3f} rho).")
    elif rho_mu < rho_wr:
        print(f"  pooled WR ranks better than frozen-panel mu ({rho_mu - rho_wr:+.3f} rho) — "
              f"the swap is NOT paying off on this evidence.")
    else:
        print("  the two metrics rank identically on this set — no evidence either way.")

    smallest_p = 2.0 / math.factorial(n)
    print(f"  At n={n} the smallest attainable two-sided p is {smallest_p:.3f} (a perfect rank "
          f"match). Treat any rho here as suggestive; the CI is the honest summary.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="Append one candidate's local + ladder measurement")
    rec.add_argument("--candidate")
    rec.add_argument("--result-json", help="output of `ladder_eval.py rate --json`")
    rec.add_argument("--panel-version")
    rec.add_argument("--local-mu")
    rec.add_argument("--local-sigma")
    rec.add_argument("--pooled-wr")
    rec.add_argument("--games")
    rec.add_argument("--submission-ref")
    rec.add_argument("--readings", nargs="*",
                     help="every ladder mu reading, oldest first; >=2 required to count as settled")
    rec.add_argument("--date", default="")
    rec.add_argument("--notes", default="")

    rep = sub.add_parser("report", help="Rank-correlate local metrics against the ladder")
    rep.add_argument("--panel-version", help="default: the version with the most rows")

    args = ap.parse_args()
    if args.cmd == "record":
        cmd_record(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    main()
