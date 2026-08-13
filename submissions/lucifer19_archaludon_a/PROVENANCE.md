# Provenance

Source: public Kaggle kernel `lucifer19/battlecore-compact-agent` ("PTCG AI Battle —
Max-Efficiency Challenger Build (V4)"), pulled to
`notebooks/kaggle-research/pulled/lucifer19__battlecore-compact-agent/battlecore-compact-agent.ipynb`.

Cleared under the 2026-08-13 third-party code decision: agents derived from public Kaggle
kernels may be submitted.

The notebook ships two profiles ("A" — Archaludon Metal Tempo, "B" — Alakazam/Dunsparce)
embedded in cell 1 as a single blob: `AGENT_PAYLOADS = json.loads(_unpack(r"""..."""))`,
where `_unpack` is `zlib.decompress(base64.b64decode(...))`. Each profile's `main_py` /
`deck_csv` fields carry their own SHA-256 (`main_hash` / `deck_hash`) which the notebook
verifies at build time. This directory extracts Profile A only, decoded the same way
(base64 → zlib → JSON) and written out directly, with the SHA-256 hashes checked before
writing — both matched, so the bytes shipped here are byte-identical to what the notebook
itself would produce and submit.

Profile A is a hardened Archaludon variant, ~0.975 similarity to
`masamikobayashi_archaludon_cinderace`. Substantively it clamps selection counts
(`max_count = max(min_count, min(max_count, len(scored)))`, `return selected[:max_count]`)
and replaces the crash-fallback `random.sample(...)` with a deterministic
`return list(range(max_count))` — the same bug class `archaludon_lossfix` fixed
(+128.5 mu), applied in more places. It lacks `archaludon_lossfix`'s `_boss_has_lethal()`
gate and the "save Lillie / attach loose Metal Energy first" rule, so the two forks fix
disjoint problems; a merged variant is a candidate follow-up if a slot remains.

Kernel claims a badge of 846.8. Never forked or measured locally before this extraction.
Never uploaded to the real ladder under this repo. Profile B (Alakazam/Dunsparce) was not
extracted — out of scope for this pass.
