---
paths:
  - "src/ladder_eval.py"
  - "src/trueskill_lite.py"
  - "src/local_eval.py"
  - "src/calibration_tracker.py"
  - "notebooks/kaggle-research/evaluation-methodology.md"
---

## Local evaluation — `ladder_eval.py` is the gate, `local_eval.py` is not

**Rank candidates with `src/ladder_eval.py`, not `src/local_eval.py`.** Full derivation and every
measurement behind this is in `notebooks/kaggle-research/evaluation-methodology.md`'s
"2026-08-09 evaluation-harness rebuild" section; the operational summary:

```bash
python3 src/ladder_eval.py rate --candidate submissions/<name> --games 4000 --workers 8 \
    --json data/processed/ratings/<name>.json
```

It rates the candidate against a **frozen** 7-agent panel (`data/processed/panel_ratings.json`,
current version `fa733a4e989a`) using a pure-Python no-draw TrueSkill (`src/trueskill_lite.py`)
with Kaggle's parameterization, and reports local μ plus per-opponent Wilson CIs. Panel ratings
are fit once and **never refit** when evaluating a candidate — that is what makes μ comparable
across candidates, and what fixes `local_eval.py:136`'s self-exclusion bias (it drops the
candidate from its own roster, so roster members face an easier field than non-members).

`local_eval.py`'s pooled win rate is superseded **for ranking**. Keep using it for its
loss-tracing (`--save-losses`, `--repeats`), which `ladder_eval.py` does not duplicate.

Things that will otherwise be re-derived the hard way:

- **The gate ranks candidates, not one-line tweaks within one archetype.** Retro-validated
  2026-08-09 against the two pairs whose ladder answer was already known: frozen-panel μ separated
  them by 4.2 and −12.4 μ where the ladder separated them by 50.1 and 63.4, i.e. "tie" both times,
  and the sign was wrong on one. A mirror head-to-head (4000 battles) and pooled WR agree it is a
  tie. Choose within-archetype changes by mechanism from reading the code, and settle them on the
  ladder. Full writeup in `evaluation-methodology.md`'s "2026-08-09 retro-validation" section.
- **Measure a branch's reachability before crediting or blaming it.** The Archaludon
  `detect_matchup` guard was treated as a −63 μ regression while firing in 0/29,064 sampled
  states. Instrument the branch and count the share of *battles* in which it fires at least once.
- **Differences under ~25 μ are noise.** Two independent 24,000-game runs of the same candidate
  moved ~12 μ against a nominal σ of ~20.
- **`rate_candidate` fits with `fit_against_fixed` (`src/trueskill_lite.py`), not the sequential
  `rate_against_fixed` filter.** The sequential filter's sigma collapses monotonically and never
  recovers, so its mu ends up decided by whichever results happen to arrive first —
  `fit_against_fixed` fits the whole result set at once (closed-form MLE, provably
  order-invariant) instead. `panel_version` hashes `candidate_estimator` so ratings from the two
  methods can never silently compare. See `notebooks/kaggle-research/10-day-plan.md`'s
  2026-08-14 "order-invariant estimator" section for the re-verification that this changed no
  existing candidate's ranking.
- **No seed control exists** — `libcg.so` self-seeds from `std::random_device` and exports no
  seeding entry point, so Common Random Numbers is impossible. Sample size is the only lever.
- **Workers must be processes, not threads** — the engine is a ctypes singleton with a
  process-global `Battle.battle_ptr`.
- **`ladder_eval.py` pins `OMP_NUM_THREADS` and friends to 1 at module top, before numpy is
  imported.** Do not move or remove this. `il_agent_v2b` pulls in a threaded BLAS, and
  unpinned it cost 24.3 s CPU per battle (54× more than pinned) and made 8 workers run 2.8×
  *slower* than serial.
- **Agents can shadow each other's helper modules.** Four IL submissions each ship their own
  `il_features.py`; in one process the first to load wins `sys.modules` and later agents silently
  get the wrong helper. `ladder_eval._load_agent_isolated` handles it. If you write a new harness
  that loads multiple `main.py` files into one process, you need the same guard.

Calibration against the real ladder (`src/calibration_tracker.py`, `data/processed/calibration.csv`):
frozen-panel μ correlates with settled ladder μ at ρ = +0.80 vs pooled WR's +0.60 — but n=5, the
CI is [+0.11, +1.00], and p = 0.133. **The frozen panel is better-founded, not yet demonstrably
predictive.** Only a real submission settles a close call. Also note a hard ceiling on any
panel-based metric: 44.3% of the real field's decks are <0.30 Jaccard-similar to *any* panel deck.

