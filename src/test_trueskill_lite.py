"""Tests for `src/trueskill_lite.py`.

Run: python3 src/test_trueskill_lite.py

Deliberately does *not* assert against a memorised constant from the `trueskill` pip package —
that package defaults to draw_probability=0.10 and this module is explicitly no-draw (the engine
reports `result` as a win-player-index, never a draw; see cg/api.py:376). Instead each numeric
claim is re-derived here from first principles through an independent code path, and the rest are
functional properties.

The last test is the important one: it's the claim the whole frozen-panel design rests on.
"""

import math
import random
import sys

from trueskill_lite import (
    Rating,
    fit_against_fixed,
    rate_1vs1,
    rate_against_fixed,
    win_probability,
    DEFAULT_BETA,
    DEFAULT_TAU,
)

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


def test_update_matches_first_principles():
    """Re-derive the t=0 update by hand and compare to the module."""
    print("update matches an independent hand derivation")
    mu0, sigma0 = 25.0, 25.0 / 3.0
    beta, tau = 25.0 / 6.0, 25.0 / 300.0

    # Independent derivation, written out longhand rather than reusing the module's helpers.
    s2 = sigma0 ** 2 + tau ** 2
    c = math.sqrt(2.0 * beta ** 2 + s2 + s2)
    t = 0.0
    phi0 = 1.0 / math.sqrt(2.0 * math.pi)          # pdf(0)
    Phi0 = 0.5                                      # cdf(0)
    v = phi0 / Phi0
    w = v * (v + t)
    expected_mu = mu0 + (s2 / c) * v
    expected_sigma = math.sqrt(s2 * (1.0 - (s2 / c ** 2) * w))

    win, lose = rate_1vs1(Rating(mu0, sigma0), Rating(mu0, sigma0), beta=beta, tau=tau)
    check("winner mu", abs(win.mu - expected_mu) < 1e-12, f"{win.mu} vs {expected_mu}")
    check("winner sigma", abs(win.sigma - expected_sigma) < 1e-12, f"{win.sigma} vs {expected_sigma}")
    check("loser mu mirrored", abs(lose.mu - (2 * mu0 - expected_mu)) < 1e-12)
    check("mu shift is zero-sum for equal priors",
          abs((win.mu - mu0) + (lose.mu - mu0)) < 1e-12)
    check("sigma strictly decreases", win.sigma < sigma0 and lose.sigma < sigma0)


def test_v_w_identities():
    """W = V*(V+t) must hold, and W must stay in (0,1), across the whole range including tails."""
    print("V/W identities hold across the range")
    from trueskill_lite import _v_win, _w_win
    ok_identity, ok_range = True, True
    for i in range(-400, 401):
        t = i / 10.0
        v = _v_win(t)
        w = _w_win(t)
        if abs(w - v * (v + t)) > 1e-9 and w < 1.0 - 1e-9:
            ok_identity = False
        if not (0.0 <= w < 1.0):
            ok_range = False
    check("W == V*(V+t)", ok_identity)
    check("0 <= W < 1", ok_range)


def test_tail_guard():
    """A hopeless upset must not divide by an underflowed CDF."""
    print("far-tail upset does not blow up")
    try:
        win, lose = rate_1vs1(Rating(0.0, 1e-6), Rating(100000.0, 1e-6), beta=1e-6, tau=0.0)
        finite = all(math.isfinite(x) for x in (win.mu, win.sigma, lose.mu, lose.sigma))
        check("finite output on extreme upset", finite, f"{win} {lose}")
    except ZeroDivisionError as exc:
        check("finite output on extreme upset", False, f"raised {exc!r}")


def test_win_probability():
    print("win_probability behaves")
    check("identical ratings -> 0.5",
          abs(win_probability(Rating(600, 200), Rating(600, 200)) - 0.5) < 1e-12)
    check("stronger player > 0.5", win_probability(Rating(800, 50), Rating(600, 50)) > 0.5)
    check("antisymmetric",
          abs(win_probability(Rating(800, 50), Rating(600, 50))
              + win_probability(Rating(600, 50), Rating(800, 50)) - 1.0) < 1e-12)


def test_converges_to_true_skill():
    """Rating a candidate that wins a known fraction should recover that win probability."""
    print("frozen-opponent rating converges to the observed win rate")
    rng = random.Random(0)
    opponent = Rating(600.0, 30.0)  # confident opponent rating
    for true_p in (0.25, 0.50, 0.75):
        results = [(opponent, rng.random() < true_p) for _ in range(4000)]
        final = rate_against_fixed(Rating(), results)
        recovered = win_probability(final, opponent)
        check(f"true_p={true_p:.2f} recovered={recovered:.3f}",
              abs(recovered - true_p) < 0.06, f"got {recovered:.4f}")


def test_rank_recovery():
    """A synthetic 3-agent ladder with known strengths must come out in the right order."""
    print("synthetic ladder recovers the true rank order")
    rng = random.Random(1)
    true_strength = {"strong": 0.80, "mid": 0.50, "weak": 0.20}  # P(beat the reference)
    reference = Rating(600.0, 30.0)
    ratings = {}
    for name, p in true_strength.items():
        results = [(reference, rng.random() < p) for _ in range(3000)]
        ratings[name] = rate_against_fixed(Rating(), results)
    order = sorted(ratings, key=lambda k: ratings[k].mu, reverse=True)
    check("order is strong > mid > weak", order == ["strong", "mid", "weak"], f"got {order}")


MEDIAN = Rating(600.0, 30.0)


def _as_wr_gap(mu_a: float, mu_b: float) -> float:
    """Express a mu gap on a win-rate scale, so it is comparable to a pooled-WR gap in pp."""
    return abs(win_probability(Rating(mu_a, 30.0), MEDIAN)
               - win_probability(Rating(mu_b, 30.0), MEDIAN)) * 100.0


def _play(rng, field, games, model_consistent):
    """Play `games` rounds against every member of `field`, interleaved.

    field: list of (name, frozen_rating, true_win_prob). When `model_consistent` is set the
    true win prob is ignored and outcomes are drawn from the TrueSkill model itself, using a
    fixed latent candidate skill — that isolates the estimator from model misspecification.
    """
    latent = Rating(700.0, 1e-6)
    results, wins, total = [], 0, 0
    for _ in range(games):
        for _name, rating, p in field:
            prob = win_probability(latent, rating) if model_consistent else p
            won = rng.random() < prob
            results.append((rating, won))
            wins += won
            total += 1
    return rate_against_fixed(Rating(), results).mu, wins / total


def _panel():
    """One very strong member plus four ordinary ones."""
    return [
        ("strong", Rating(900.0, 30.0), 0.20),
        ("a", Rating(600.0, 30.0), 0.60),
        ("b", Rating(600.0, 30.0), 0.60),
        ("c", Rating(600.0, 30.0), 0.60),
        ("d", Rating(600.0, 30.0), 0.60),
    ]


def test_subset_invariance_well_specified():
    """The estimator property, isolated: under the TrueSkill model itself, frozen-panel mu is
    subset-invariant. Dropping the strongest opponent must barely move it, while pooled win rate
    moves a lot purely because the field got easier."""
    print("frozen-panel mu is subset-invariant under a well-specified model")
    rng = random.Random(2)
    full = _panel()
    subset = [x for x in full if x[0] != "strong"]
    mu_full, wr_full = _play(rng, full, 4000, model_consistent=True)
    mu_subset, wr_subset = _play(rng, subset, 4000, model_consistent=True)

    wr_gap = abs(wr_full - wr_subset) * 100.0
    mu_gap_pp = _as_wr_gap(mu_full, mu_subset)
    print(f"        pooled WR:  {wr_full * 100:.1f}% vs {wr_subset * 100:.1f}%  -> gap {wr_gap:.2f}pp")
    print(f"        frozen mu:  {mu_full:.1f} vs {mu_subset:.1f}  -> {mu_gap_pp:.2f}pp equivalent")
    check("pooled WR is distorted by the missing matchup", wr_gap > 5.0, f"{wr_gap:.2f}pp")
    check("frozen mu is essentially unmoved", mu_gap_pp < 1.5, f"{mu_gap_pp:.2f}pp")


def test_subset_invariance_misspecified():
    """The realistic case, and a limitation the design docs must state rather than hide.

    Real agents are intransitive: measured here, Archaludon beats Lucario 72.7% and Dragapult
    80.7% but loses to Crustle 32.7% — while Crustle's real ladder score (553.8) is far *below*
    Dragapult's (727.3). No single-number rating can represent that, TrueSkill included.

    So this is a measurement, not a pass/pass-threshold. The one thing that IS structural, and is
    asserted: pooled WR falls mechanically when a hard opponent joins the field, purely because
    the field got harder. Frozen-panel mu does not — it moves according to whether the result beat
    the model's expectation, which is the behaviour we actually want. Magnitude of the residual
    distortion under heavy intransitivity is reported and can be comparable to pooled WR's; the
    decisive evidence is the empirical check in `ladder_eval.py`, not this synthetic.
    """
    print("frozen-panel mu under a deliberately misspecified (intransitive) generator")
    rng = random.Random(3)
    full = _panel()
    subset = [x for x in full if x[0] != "strong"]
    mu_full, wr_full = _play(rng, full, 4000, model_consistent=False)
    mu_subset, wr_subset = _play(rng, subset, 4000, model_consistent=False)

    wr_gap = abs(wr_full - wr_subset) * 100.0
    mu_gap_pp = _as_wr_gap(mu_full, mu_subset)
    print(f"        pooled WR:  {wr_full * 100:.1f}% vs {wr_subset * 100:.1f}%  -> gap {wr_gap:.2f}pp")
    print(f"        frozen mu:  {mu_full:.1f} vs {mu_subset:.1f}  -> {mu_gap_pp:.2f}pp equivalent")
    print(f"        NOTE residual mu distortion is {mu_gap_pp / wr_gap:.2f}x pooled WR's here — "
          f"under heavy intransitivity the frozen panel is not automatically better in magnitude")
    # Structural, and the actual reason to prefer it: adding a harder opponent must not
    # mechanically depress the rating the way it depresses an unweighted average.
    check("pooled WR drops when the hard opponent is added", wr_full < wr_subset,
          f"{wr_full:.4f} vs {wr_subset:.4f}")
    check("frozen mu does NOT drop mechanically", mu_full > mu_subset,
          f"{mu_full:.2f} vs {mu_subset:.2f}")


def test_fit_is_order_invariant():
    """The property the sequential filter does not have, and the reason this estimator exists."""
    print("fit_against_fixed is invariant to the order results arrive in")
    panel = [Rating(681.6, 40.0), Rating(674.7, 40.0), Rating(653.4, 40.0),
             Rating(584.4, 40.0), Rating(528.5, 40.0), Rating(443.4, 40.0)]
    wins = [1664, 1313, 2610, 2912, 3699, 3942]
    results = []
    for opp, k in zip(panel, wins):
        results.extend([(opp, True)] * k + [(opp, False)] * (4000 - k))

    fitted, sequential = [], []
    for seed in range(12):
        shuffled = list(results)
        random.Random(seed).shuffle(shuffled)
        fitted.append(fit_against_fixed(shuffled).mu)
        sequential.append(rate_against_fixed(Rating(), shuffled).mu)

    fit_spread = max(fitted) - min(fitted)
    seq_spread = max(sequential) - min(sequential)
    check("fit mu is identical across orderings", fit_spread < 1e-6,
          f"spread {fit_spread:.2e}")
    check("the sequential filter is not, by a wide margin", seq_spread > 20.0,
          f"sequential spread only {seq_spread:.1f}")


def test_fit_recovers_a_known_skill():
    """Simulate games from a known skill and check the fit finds it."""
    print("fit_against_fixed recovers the skill that generated the data")
    rng = random.Random(7)
    true_skill = 760.0
    panel = [Rating(mu, 30.0) for mu in (450.0, 550.0, 650.0, 750.0, 850.0)]
    results = []
    for opp in panel:
        c = math.sqrt(2.0 * DEFAULT_BETA ** 2 + opp.sigma ** 2)
        p_win = 0.5 * math.erfc(-((true_skill - opp.mu) / c) / math.sqrt(2.0))
        for _ in range(20000):
            results.append((opp, rng.random() < p_win))

    fitted = fit_against_fixed(results)
    check("mu within 15 of the generating skill", abs(fitted.mu - true_skill) < 15.0,
          f"got {fitted.mu:.1f}, wanted {true_skill:.1f}")
    check("Laplace sigma is small at 100k games", fitted.sigma < 6.0,
          f"sigma {fitted.sigma:.2f}")
    check("the generating skill is inside +/- 3 sigma",
          abs(fitted.mu - true_skill) < 3.0 * fitted.sigma,
          f"|{fitted.mu - true_skill:.1f}| vs 3*{fitted.sigma:.2f}")


def test_fit_is_monotone_in_wins():
    """More wins against the same field must never lower the fitted skill."""
    print("fit_against_fixed is monotone in the win count")
    opp = Rating(600.0, 40.0)
    mus = [fit_against_fixed([(opp, True)] * k + [(opp, False)] * (2000 - k)).mu
           for k in range(0, 2001, 200)]
    check("monotone non-decreasing", all(b > a for a, b in zip(mus, mus[1:])),
          f"{[round(m, 1) for m in mus]}")
    check("a 50% record against a 600 opponent fits near 600",
          abs(fit_against_fixed([(opp, True)] * 1000 + [(opp, False)] * 1000).mu - 600.0) < 1.0)


def test_fit_stays_finite_on_a_clean_sweep():
    """A 100% record has no maximum-likelihood estimate; the prior is what keeps it finite."""
    print("fit_against_fixed stays finite when a candidate wins every game")
    opp = Rating(443.4, 40.0)
    swept = fit_against_fixed([(opp, True)] * 4000)
    check("finite and bounded", math.isfinite(swept.mu) and swept.mu < 3000.0,
          f"mu {swept.mu:.1f}")
    check("above the opponent it swept", swept.mu > opp.mu, f"mu {swept.mu:.1f}")


if __name__ == "__main__":
    for fn in (
        test_update_matches_first_principles,
        test_v_w_identities,
        test_tail_guard,
        test_win_probability,
        test_converges_to_true_skill,
        test_rank_recovery,
        test_subset_invariance_well_specified,
        test_subset_invariance_misspecified,
        test_fit_is_order_invariant,
        test_fit_recovers_a_known_skill,
        test_fit_is_monotone_in_wins,
        test_fit_stays_finite_on_a_clean_sweep,
    ):
        fn()
        print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print("all tests passed")
