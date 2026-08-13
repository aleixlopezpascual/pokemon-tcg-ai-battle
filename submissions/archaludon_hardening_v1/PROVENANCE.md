# Provenance

Reconstruction, not a fresh agent. Our own genuine best real score (774.8, ref `55327510`)
was never preserved as source — only `55330407`'s later, guarded state survived, as
`submissions/masamikobayashi_archaludon_cinderace/main.py`.

`55327510` (774.8) and `55330407` (711.4) differ by exactly one change: `55330407` added a
`None`-filter in `detect_matchup` to guard against a face-down opponent active crashing the
`p.id` lookup. That guard was measured to fire **0/171,566** times in the original real-data
sample and **0/200** in a local smoke test run here before reverting it. The two states are
behaviourally identical; the 63.4 mu gap between their real readings (774.8 vs 711.4) is
ladder noise, not a real effect of the fix.

This directory is `masamikobayashi_archaludon_cinderace/main.py` with that filter reverted,
reconstructing `55327510`'s exact behavior. See `notebooks/kaggle-research/10-day-plan.md`
line 168 and `evaluation-methodology.md` line 218 for the original measurement.
