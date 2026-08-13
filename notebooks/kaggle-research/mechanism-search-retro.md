# Mechanism-search retrospective (IL + rating/behavior prior + deck mining), 2026-08-07 to 2026-08-13

**Status at close: no new agent beats the existing roster. Best real submission remains
`soutasakurai_libraryout_crustle` at 744.6. This effort is exhausted for the 2026-08-16 deadline;
remaining runway should go to real-ladder confirmation reads and manual Final Submission
selection (lever L7), not further model/rule engineering.**

## What was tried, in order

### Track 1 — standalone IL scorer (v1/v2/v2b/v3)

Trained a scorer directly on replay data to imitate expert decisions.

- v1: real score 446.0, well below rule-based baseline (~690).
- v2: fixed a 22% obs/action mislabeling bug and 0%-resolved card-identity for MAIN options. Real
  523.1/531.8. Still far below baseline. First submit ERRORed (sklearn needs numpy/pandas — the
  Kaggle sandbox has neither); fixed by exporting the tree to a pure-Python JSON predictor
  (`src/pure_predictor.py`), verified bit-identical to sklearn's own `predict_proba`.
- v2b: local frozen-panel μ 532.2, never submitted (no improvement over v2).
- v3: scaled data, ELO-weighted sampling, guardrail layer, new features. Passed its own offline
  accuracy gate but scored 30.3% pooled win rate locally — worse than v2. Traced to the retrain
  itself, not guardrails or export/packaging (both independently verified clean).
- Tested and ruled out a covariate-shift explanation for why IL kept losing: IL self-play states
  separate from the training corpus at AUC 0.979, but a non-IL control agent separates even
  *higher* (0.998) against the same panel. The separation is panel-vs-real-ladder mismatch, not
  IL-specific trajectory drift — a DAgger-style fix would not have helped.
- **Frozen twice. Standalone IL is dead for this deadline.**

**Lesson:** an IL scorer trained on general (not deck-scoped, not skill-filtered) replay data
reproduces the corpus's average quality, which is below what a hand-tuned rule-based scorer
already achieves for a well-optimized archetype. More data of the same kind does not fix this —
the ceiling is set by what fraction of the corpus is actually expert play for *your* deck.

### Track 2 — 5-class intent classifier as PIMC gate (Task 14)

Idea: predict which of 5 intents (aggro/base/develop/snipe/survive) a full PIMC search would
pick, and skip the expensive search most of the time.

- Held-out accuracy 85.7% — already below the majority-class baseline of 87.7% (bad class
  imbalance: develop n=6, snipe n=93, survive n=58 training examples). This was a known red flag
  at training time and the model was wired in anyway.
- Wired as the primary decision (PIMC as tiebreaker only). Gate result: pooled win rate 39.0%,
  worse than doing nothing (41.9% baseline). Mirror matchup collapsed from 50% to 36.3% — the
  worst regression of any lever tried in this whole effort.
- Five follow-up iterations tried to rescue the mechanism (noise-driven override, energy
  visibility fix, IL contingency, override-gate regression-test fix) — all failed or reproduced
  the same or worse pooled rate. Root-caused: the underlying classifier accuracy problem, not any
  of the integration bugs fixed along the way.

**Lesson (the one that mattered most for everything after):** an offline classifier accuracy
*below* the majority-class baseline is a hard stop. Do not wire it in "to see what happens" —
that costs a full gate cycle (and in this case, five more) to rediscover what the offline number
already said. This lesson is exactly why Task 8 in the next effort (below) pre-registered G3a
("must beat availability-baseline by ≥5pp") as a gate *before* any agent code was written.

### Track 3 — rating + behavior-filtered class prior on Crustle (`crustle_il`, levers L0-L6)

Followed the Orbit Wars 2nd-place writeup's fix: filter training data by rating **and**
behavior/deck-archetype, shrink the label space to match a simplified action space, and gate
every step against pre-registered falsifiers before spending battle budget.

**Base switch, forced by measurement.** Archaludon's deck has max multiset Jaccard 0.200 against
7,877 corpus sides — indistinguishable from the unrelated-deck floor (0.176). A deck-scoped
behavior filter is dead on Archaludon. Crustle's deck clears Jaccard ≥ 0.30 against 566 corpus
sides (21,104 MAIN records) — the only scored-architecture agent with real corpus coverage. All
further measurement re-ran on Crustle, not carried over from Archaludon numbers.

**Confounder found before any model was trained.** Class mix by rating band alone moves ≤2.7pp
per class — rating is not the active ingredient. Class mix by deck-archetype cluster moves
8-13pp per class — deck archetype is the dominant confounder of "what class of move gets played."
A prior trained without deck-scoping would learn the meta's action mix, not skill.

**The reallocatable ceiling is thin.** Availability-matched total-variation distance between the
Archaludon agent and the expert corpus was 8.75pp total, with 7.0pp of that in a single class
(EVOLVE). A perfect class prior has at most ~8.75pp of decisions to touch. Separately, 21.5% of
MAIN decisions have ≥2 options tied at the top score (99.1% of that within-class) — a large pool
of genuine indifference a class-level prior structurally cannot help, since it doesn't touch
ties. Cross-class decisions with a score margin <100 (the class prior's realistic reachable pool)
were only 7.6% — for comparison, a related PIMC mechanism (Track 2) died at ~3% reachability.

**Reachability gate, re-measured live on Crustle, failed at the scope that mattered.** The
plan's L0/L0b levers needed ≥5% of *MAIN-context* decisions to have a genuine (non-idx-fallback)
distinguishable tie or gap to act on. Measured: 2.20% of all examined states / 3.34% of
MAIN-context states — both below the 5% floor. A broader, unfiltered scope (including
deck-search / bench-select decisions outside MAIN, dominated by one option type) did clear
5.62-6.04%, but that is a materially different, narrower-value lever than what L0/L0b/L5 were
built to test, and was flagged separately rather than substituted in.

**Consequence:** because reachability failed at the scope the whole class-prior mechanism
depended on, the plan's own calendar rule ("if reachability fails, skip model training entirely")
correctly routed past L1-L4 (the trained-prior gates) without spending any training or battle
budget on them. This is the effort's biggest efficiency win: a ~30-minute measurement correctly
predicted that a multi-day model-training effort would fail, and skipped it.

**L6 — deck mining (no ML, no reachability dependency).** Clustered the corpus once
(`actor_score ≥ 1100`, threshold 0.7), found 3 clusters clearing `games≥30` / `WR≥60%`, matched 2
against existing submissions: `kiyota_mega_lucario_ex` (jaccard 0.714, cluster at 244 games/63.9%
WR) and `kiyota_dragapult_ex` (jaccard 0.739, cluster at 142 games/62.7% WR). Built deck-swapped
forks, smoke-tested clean, measured local panel μ at matched game counts:

| candidate | stock μ (local) | swapped μ (local) | Δ | verdict (local) |
|---|---|---|---|---|
| `kiyota_mega_lucario_ex` | 582.4 | 573.5 | −8.9 | wash, inside 25μ noise band |
| `kiyota_dragapult_ex` | 617.3 | 500.9 | −116.4 | clear regression |

Both failed the local falsifier. Plan's 2-iteration-per-lever cap was already exhausted (no
further qualifying clusters existed anyway).

**All six levers (L0, L0b, L1-L4 skipped, L5, L6) now exhausted or failed within the runway.**
This is the finding that closed out the whole mechanism-search effort and routed to L7.

## The real-ladder divergence test (2026-08-12/13) — the one deliberate exception to "local FAIL kills it"

`evaluation-methodology.md`'s calibration table already showed (n=5, not statistically
significant, Spearman ρ=+0.800) that local μ can diverge from, or even invert relative to, real
ladder μ for specific archetypes — most notably `kiyota_dragapult_ex` (local 615.9-617.3 vs real
698.5, real *higher*) and `kiyota_mega_lucario_ex` (local ~582-591 vs real only 439.9-450.9, real
*much lower*).

Rather than discard both locally-failed L6 forks outright, both were submitted for a real
reading, spending 2 of the day's 5 upload slots specifically to test whether the documented
calibration mismatch would rescue either candidate.

**Settled real readings:**

| candidate | local verdict | real reading | parent's real reading | outcome |
|---|---|---|---|---|
| `kiyota_mega_lucario_ex_l6deck` | wash (Δ −8.9) | **516.4** | 439.9-450.9 | **real improvement, +66 to +76** |
| `kiyota_dragapult_ex_l6deck` | clear regression (Δ −116.4) | **581.7** | 698.5 | real regression, same direction as local |

**Result: 1 of 2 flipped sign. 1 of 2 agreed with local.**

**The generalizable lesson, now confirmed by a live A/B rather than only the earlier
retrospective table:** local μ (TrueSkill on the small frozen panel) is not reliable enough to
*kill* a within-archetype change on its own — it correctly predicted the dragapult outcome but
completely missed the mega_lucario improvement. It is also not useless — it got dragapult right.
The practical rule this justifies: **when daily upload quota allows it, verify a locally-marginal
or locally-failed within-archetype candidate on the real ladder before permanently discarding it,
especially for archetypes/changes similar in kind to ones with documented local/real
divergence.** This does not extend to candidates that fail by a large margin against a
*different*, dissimilar baseline (e.g. Track 1/Track 2's failures against rule-based agents were
never close enough to be plausible local-instrument noise).

**Important caveat on magnitude:** even the winning case, 516.4, remains far below the roster's
actual best (744.6). This test resolved a local/real calibration question; it did not produce a
new best agent.

## Net outcome and what's still true

- No agent produced in this session beats the existing roster. The standing objective ("an agent
  that beats all our others locally") remains unmet by anything from Tracks 1-3 or the L6 forks.
- Best real submission is unchanged: `soutasakurai_libraryout_crustle`, 744.6 (ref `55416420`).
- The mechanism-search path (trained scorers, trained class priors, rule edits, deck mining) is
  exhausted for this deadline — every lever failed its own pre-registered falsifier, and the
  plan's own escalation table has no further step short of L7.
- One methodological finding survives past this deadline and is worth carrying into future
  sessions/competitions: **the local TrueSkill panel is a weak, not strong, instrument for
  within-archetype tweaks — real-ladder verification is warranted for marginal/failed local
  reads whenever quota allows, but a local pass/fail decision that's later reversed by real data
  usually only reverses in one direction at a time, not systematically.**
