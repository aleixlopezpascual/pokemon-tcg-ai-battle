"""Minimal TrueSkill (1v1, no draws) in pure Python.

Why not `pip install trueskill`: it isn't installed here, and more importantly the whole point
of this module is that the update rule is *visible* and matchable to Kaggle's. The competition
reports a TrueSkill-style N(mu, sigma^2) per team, so the local evaluation metric should be the
same functional, not a pooled win rate — pooled win rate weights every opponent equally, whereas
a rating system weights by opponent strength. That difference is exactly why pooled win rate
inverts rankings between comparable candidates here (see `notebooks/kaggle-research/
evaluation-methodology.md`).

The key property this module buys us: with opponent ratings *held fixed*, a candidate's posterior
mu is, in expectation, invariant to which subset of the panel it played. Pooled win rate is not —
it is biased by the strength of whichever opponents happened to be in the field. That is what
makes a frozen-panel rating the right fix for `local_eval.py`'s self-exclusion bias rather than a
patch over it.

Defaults are Kaggle's simulation-competition defaults (mu0=600, sigma0=200, beta=sigma0/2,
tau=sigma0/100). Our observed real ladder scores span ~440-1200, consistent with those.

Only stdlib (`math`) is used, so this can also be imported from a submission if ever needed.
"""

import math

DEFAULT_MU = 600.0
DEFAULT_SIGMA = 200.0
DEFAULT_BETA = DEFAULT_SIGMA / 2.0
DEFAULT_TAU = DEFAULT_SIGMA / 100.0


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _cdf(x: float) -> float:
    """Standard normal CDF, via erfc rather than 1+erf.

    `0.5 * (1 + erf(x/sqrt2))` catastrophically cancels in the left tail: erf saturates at -1.0
    in double precision around x = -6, so the expression returns *exactly* 0.0 for every
    x < ~-29 — losing the answer entirely, not merely some precision. The erfc form stays
    accurate down to ~x = -38, where the result genuinely underflows.
    """
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# Below this, erfc itself underflows and we switch to the asymptotic expansion. Chosen with
# margin: _cdf stays nonzero to about t = -38.
_TAIL_T = -37.0


def _v_and_w(t: float) -> tuple[float, float]:
    """Return (v, w) where v is the truncated-Gaussian mean multiplier and w = v*(v+t).

    v answers "how surprising was this result" and w is the corresponding variance multiplier.

    Both are computed together because `w` needs `v + t`, and for very negative t that sum is a
    catastrophic cancellation: v -> -t, so the two terms are large and nearly equal. Computing
    `v + t` from its own asymptotic series instead of by subtraction keeps w accurate and keeps
    the identity w == v*(v+t) exact by construction.

    Asymptotic for t -> -inf, with u = -t (Mills ratio expansion):
        v       ~ u + 1/u - 2/u^3
        v + t   ~     1/u - 2/u^3
        w       -> 1
    In practice t = (mu_w - mu_l)/c and c >= 2*beta, so |t| stays well under 10 for any realistic
    rating pair; the tail branch exists so the function is total, not because it is hot.
    """
    if t > _TAIL_T:
        denom = _cdf(t)
        v = _pdf(t) / denom
        return v, v * (v + t)

    u = -t
    v_plus_t = 1.0 / u - 2.0 / (u ** 3)
    v = u + v_plus_t
    return v, v * v_plus_t


def _v_win(t: float) -> float:
    return _v_and_w(t)[0]


def _w_win(t: float) -> float:
    """Variance multiplier; analytically in (0, 1), clamped against float drift."""
    return min(1.0 - 1e-12, max(0.0, _v_and_w(t)[1]))


class Rating:
    __slots__ = ("mu", "sigma")

    def __init__(self, mu: float = DEFAULT_MU, sigma: float = DEFAULT_SIGMA):
        self.mu = float(mu)
        self.sigma = float(sigma)

    def __repr__(self):
        return f"Rating(mu={self.mu:.2f}, sigma={self.sigma:.2f})"

    def as_dict(self) -> dict:
        return {"mu": self.mu, "sigma": self.sigma}

    @classmethod
    def from_dict(cls, d: dict) -> "Rating":
        return cls(d["mu"], d["sigma"])


def rate_1vs1(winner: Rating, loser: Rating, beta: float = DEFAULT_BETA,
              tau: float = DEFAULT_TAU) -> tuple[Rating, Rating]:
    """Return updated (winner, loser) ratings after one decisive game.

    Standard TrueSkill 1v1 no-draw update. `tau` (dynamics) is added to the variance before the
    update so ratings never fully freeze.
    """
    w_sigma_sq = winner.sigma ** 2 + tau ** 2
    l_sigma_sq = loser.sigma ** 2 + tau ** 2
    c = math.sqrt(2.0 * beta ** 2 + w_sigma_sq + l_sigma_sq)

    t = (winner.mu - loser.mu) / c
    v, w = _v_and_w(t)
    w = min(1.0 - 1e-12, max(0.0, w))

    new_winner = Rating(
        mu=winner.mu + (w_sigma_sq / c) * v,
        sigma=math.sqrt(max(1e-12, w_sigma_sq * (1.0 - (w_sigma_sq / c ** 2) * w))),
    )
    new_loser = Rating(
        mu=loser.mu - (l_sigma_sq / c) * v,
        sigma=math.sqrt(max(1e-12, l_sigma_sq * (1.0 - (l_sigma_sq / c ** 2) * w))),
    )
    return new_winner, new_loser


def win_probability(a: Rating, b: Rating, beta: float = DEFAULT_BETA) -> float:
    """P(a beats b) under the TrueSkill model."""
    denom = math.sqrt(2.0 * beta ** 2 + a.sigma ** 2 + b.sigma ** 2)
    return _cdf((a.mu - b.mu) / denom)


def rate_against_fixed(candidate: Rating, results: list[tuple[Rating, bool]],
                       beta: float = DEFAULT_BETA, tau: float = DEFAULT_TAU) -> Rating:
    """Rate a candidate against opponents whose ratings are FROZEN.

    `results` is a list of (opponent_rating, candidate_won). Only the candidate's rating is
    carried forward between games; the opponent's posterior is discarded each time. This is the
    core of the frozen-panel design — every candidate is measured against the identical yardstick,
    and a candidate can never perturb the reference frame by being strong or weak.

    Results are consumed in the order given. Callers should interleave opponents (rather than
    playing all games vs opponent A, then all vs B) so the running sigma shrinks evenly across
    the field; `ladder_eval.py` does this.
    """
    rating = Rating(candidate.mu, candidate.sigma)
    for opponent, won in results:
        if won:
            rating, _ = rate_1vs1(rating, opponent, beta=beta, tau=tau)
        else:
            _, rating = rate_1vs1(opponent, rating, beta=beta, tau=tau)
    return rating
