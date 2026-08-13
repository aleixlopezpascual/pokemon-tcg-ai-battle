# Provenance

Source: public Kaggle kernel `jazivxt/codex-sol-eclipse-alakazam` ("Codex Sol Eclipse
Alakazam"), pulled to
`notebooks/kaggle-research/pulled/jazivxt__codex-sol-eclipse-alakazam/codex-sol-eclipse-alakazam.py`.
`romanrozen/strong-start-baseline-agent-v10-lb-950` ships byte-identical content apart from
a trailing newline; this directory credits `jazivxt` as the extracted source.

Cleared under the 2026-08-13 third-party code decision: agents derived from public Kaggle
kernels may be submitted.

The pulled file is a notebook-cell packaging script, not the agent itself: it defines
`MAIN_SOURCE` (55,611 chars) and `DECK_SOURCE` as raw string literals and writes them out
to `/kaggle/working/main.py` and `deck.csv` at submission-build time. This directory's
`main.py` and `deck.csv` are those two string literals extracted verbatim (via a regex
match on the `r'''...'''` bounds) and written to disk directly — no other transformation.

Architecturally distinct from everything else in this repo: an evolutionary-tuned `WEIGHTS`
dict of dozens of named priority weights (`play_pokemon_base`, `play_abra_early`,
`poffin_early`, `rare_candy`, `hammer_target`, etc.) feeding a real 2-ply determinized
minimax (`_search_decide`), rather than a single-ply scored-option heuristic. Deck
resolution already uses the exec-safe `globals().get("__file__")` pattern (no fallback
ladder needed here). An optional `alak_w.json` weight-override probe is present but
`os.path.exists`-guarded and unused unless that file is shipped alongside `main.py`; the
genome is baked into `WEIGHTS` so the probe file is intentionally not shipped.

Claimed by kernel title: "LB 950+"; visible badges 865.5 / 840.3. Never forked or measured
locally before this extraction. Never uploaded to the real ladder under this repo.
