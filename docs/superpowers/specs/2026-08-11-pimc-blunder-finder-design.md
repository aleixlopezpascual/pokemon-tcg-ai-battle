# PIMC-Oracle Blunder Finder — Design

## Context

`notebooks/kaggle-research/orbit-wars-teardown.md` motivated a forward-search layer
(`submissions/archaludon_intent/`) built and gated across a 14-task plan (see
`docs/superpowers/plans/check-this-doc-notebooks-kaggle-research-cosmic-flame.md` and its ledger).
Five gate attempts landed at best baseline parity; a sixth ad-hoc diagnostic
(`notebooks/kaggle-research/10-day-plan.md`'s 2026-08-11 section) root-caused why: the search
layer's PIMC-confirmation step only ever fires on ~25% of PIMC-eligible decisions (where
`classify_intent` disagrees with the base policy) and only survives its margin check ~12% of the
time, so it changes the agent's actual move on **~3% of decisions overall**. A mechanism touching
3% of decisions cannot clear a 1000-game gate even if every override it makes is a real
improvement — this is a structural ceiling of the "search reopens the decision at the moment it
disagrees" design, not a tunable bug.

That means **97% of decisions are still made by the un-searched base heuristic**
(`score_option` and its sub-scorers in `submissions/masamikobayashi_archaludon_cinderace/main.py`,
the real shipped fallback). Separately, the two biggest real, ladder-confirmed wins this whole
project has produced both came from fixing base-heuristic bugs, not from search: the `random.sample`
clip fix (+128.5 μ, `10-day-plan.md:96`) and the `detect_matchup` None-active guard
(`baseline-comparison.md:134`). No one has yet loss-traced the base heuristic specifically against
its two worst matchups (`soutasakurai_libraryout_crustle` 33.5%, `biohack44_alakazam_dunsparce`
42.1%, both far below the mirror's 50.0% — see the plan's "Reference: numbers this plan is measured
against" table). This is the untried, highest-leverage mechanism.

## Goal

Find and fix concrete base-heuristic scoring bugs in the Archaludon policy, prioritized by an
objective measure of how much each one costs, and ship a candidate that beats
`masamikobayashi_archaludon_cinderace` on the full frozen-panel gate (`src/ladder_eval.py`).

## Approach

Reuse the PIMC machinery already built and tested in `submissions/archaludon_intent/` (Tasks 1-10
of the prior plan: `rank_options`, `_pimc_score_lines`, the generic deck-agnostic opponent rollout
policy, paired determinizations) — but as an **offline diagnostic oracle**, not a live
decision-maker. Confirmed by direct code diff
(`diff submissions/masamikobayashi_archaludon_cinderace/main.py submissions/archaludon_search/main.py`):
`archaludon_search`/`archaludon_intent`'s `score_option` is the same base heuristic as the real
shipped fallback's, with a search layer appended after it — the PIMC infra can score the exact
same decisions the fallback actually makes.

Every real game is played entirely by the unmodified base heuristic (no live override — this is
not a rerun of the search-layer track). In parallel, at every MAIN decision, the diagnostic PIMC-
scores the heuristic's #1 ranked option against its next-K alternatives from `rank_options`. A
large value gap between the chosen option and the best alternative, in a game the agent went on to
lose, is a candidate blunder — an objective, ranked worklist instead of manually skimming replay
JSON and guessing which losses matter.

## Components

1. **`src/blunder_finder.py`** (new, committed). Modeled on `src/search_telemetry.py`'s worker/pool
   structure (same process-based parallelism, same `PTCG_SEARCH_PROFILE=fast`-style cost knob).
   Plays N games of the unmodified base heuristic vs one opponent. At every MAIN decision:
   compute `rank_options(obs)`, take the top `K` (default 4) distinct first-actions as `lines`,
   score them with `_pimc_score_lines` (shared/paired determinizations, per the existing paired-
   determinization design), and append one JSONL record: `{game_id, turn, chosen_option,
   chosen_value, best_alt_option, best_alt_value, gap, game_result}`. `game_result` is filled in
   after the game finishes (win/loss/draw for the candidate).
2. **Harvest runs** vs `soutasakurai_libraryout_crustle` and `biohack44_alakazam_dunsparce` (its
   two worst matchups) at N large enough to surface a useful number of high-gap decisions in lost
   games — cost is not a constraint per the user's explicit instruction; default to at least
   several hundred games per matchup, more if the top-gap worklist is thin.
3. **Triage.** Sort records by `gap`, restricted to `game_result == "loss"`. Deduplicate near-
   identical recurring situations (same `turn`-range archetype pattern) so one bug isn't counted
   as N separate findings. For each top offender, read the actual decision context — the captured
   `obs` state and the specific `score_option`/sub-scorer path that produced the chosen value —
   using the `game-engine-analyst` agent or direct code + replay reading, to find the concrete root
   cause (a missing case, an inverted comparison, a magic number that doesn't generalize past the
   matchup it was tuned on, etc. — the same defect shapes as the two confirmed historical wins).
4. **Fix target: a fresh fork of the real fallback**, `submissions/archaludon_lossfix/`, copied
   from `submissions/masamikobayashi_archaludon_cinderace/` (not from `archaludon_intent` — no
   search-layer code, stays lean, matches what would actually ship). Each fix is TDD'd against a
   captured-fixture test (same pattern as the prior plan's `src/test_search_layer.py`:
   `_load_candidate`/`load_fixture` helpers, skip cleanly when fixtures/candidate are absent).
5. **Gate:** every accumulated batch of fixes is checked against the **full frozen panel**
   (`src/ladder_eval.py rate --candidate submissions/archaludon_lossfix`), not just Crustle/
   Alakazam — a fix that helps the two worst matchups but regresses the mirror or others must be
   caught before it's credited. Ship only once the gate shows a real (>25 μ, per CLAUDE.md's noise
   floor) improvement over the current best committed number (676.3, per the prior plan's reference
   table) — or, if this repeats that plan's parity outcome, the plan's own stop condition applies:
   stop, ship the current best fallback.
6. **Fallback to manual reading (approach 1).** If the PIMC-oracle triage runs dry — no more
   high-gap decisions in the harvested losses, or applied fixes stop moving the ladder-eval gate —
   switch to `local_eval.py --save-losses --repeats` and read remaining loss replays by hand for
   patterns the oracle can't see (e.g. a systematically bad *sequence* of individually-locally-
   optimal decisions, which a single-decision value-gap metric won't surface).

## Data flow

```
base heuristic (score_option, unmodified) --plays--> real game
                    |
                    v
      rank_options(obs) top-K distinct first actions
                    |
                    v
      _pimc_score_lines (shared determinizations, paired)
                    |
                    v
      JSONL record per MAIN decision (chosen vs best-alt value, game outcome)
                    |
                    v
      triage: sort by gap, filter to losses, dedupe
                    |
                    v
      root-cause read (game-engine-analyst / replay) -> concrete bug
                    |
                    v
      fix lands in submissions/archaludon_lossfix/main.py, TDD'd
                    |
                    v
      ladder_eval.py full-panel gate
```

## Error handling

Same fail-closed discipline as the search layer: any exception inside the diagnostic's PIMC
scoring is caught and the record simply omits `best_alt_value` for that decision (never crashes
the real game, since the diagnostic never influences the actual move). The blunder-finder script
itself is a read-only instrument — it never writes to the candidate's own state.

## Testing

- `src/blunder_finder.py` is exercised the same way `src/search_telemetry.py` was: a small local
  smoke run (few games, `--workers 1`) before any large harvest, checking for tracebacks and a
  non-empty JSONL output.
- Each heuristic fix in `submissions/archaludon_lossfix/main.py` gets a fixture-driven unit test
  in a new `src/test_lossfix.py` (same `_load_candidate`/`load_fixture`/skip-cleanly pattern as
  `src/test_search_layer.py`), pinning the specific before/after scoring behavior.
- Final arbiter is `src/ladder_eval.py`'s full frozen-panel rate, per repo convention — no
  fix is credited on Crustle/Alakazam-only numbers alone.

## Out of scope

- No changes to `submissions/archaludon_intent/` or the search-layer track — it stays parked as a
  negative result, not deleted (per the prior plan's own artifacts).
- No IL/ML component of any kind (three prior IL attempts have all underperformed rule-based here;
  see `CLAUDE.md`'s "IL track frozen" note).
- No deck-list (`deck.csv`) changes in this pass — pure agent-logic fixes only. Deck-build changes
  (brainstorm option B) remain a live option for later if this track also stalls.
