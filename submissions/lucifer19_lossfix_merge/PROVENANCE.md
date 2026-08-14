# Provenance

Base: `submissions/lucifer19_archaludon_a`, itself a byte-identical extraction of Profile A
from the public Kaggle kernel `lucifer19/battlecore-compact-agent`. Cleared under the
2026-08-13 third-party code decision (public Kaggle kernels may be submitted).

This directory's deltas are authored in this repo and grafted from
`submissions/archaludon_lossfix`, which itself derives from
`submissions/masamikobayashi_archaludon_cinderace` (the shared base of all three agents).

## Why a graft, not a from-scratch tweak

`lucifer19_archaludon_a` changed only plumbing relative to base (a docstring, two None-guards,
`choose_options`'s count clamping, the crash fallback) -- every card-play scoring function is
byte-identical to base. `archaludon_lossfix` changed the opposite set: card-play heuristics,
zero plumbing. `git merge-file -p --diff3 lossfix base lucifer19` exits 0 -- the two change
sets are disjoint (nearest base-coordinate approach: 84 lines), confirmed before writing a
single line here. This is a clean graft, not a merge.

## Heuristic grafts (from `archaludon_lossfix`)

1. **`_boss_has_lethal(obs)`** (new function, inserted between `ITEMS = {...}` and
   `score_play`) -- true iff Boss's Orders would score a genuine 20000/"LETHAL Boss" this
   turn. Mirrors the lethal-only branches inside the BOSS scorer so callers can gate on
   "Boss is actually worth playing," not just "Boss is in hand with an attacker ready."
2. **Lillie branch in `score_play`** -- the Boss-save exception now requires
   `_boss_has_lethal(obs)`, not just an attacker being ready. Also adds a new branch: with a
   loose Metal Energy in hand and no lethal Boss, save Lillie (1500) to let the energy attach
   land first, instead of playing Lillie outright (5000).
3. **`apply_overrides`'s Crustle bench-attach gate** -- the `+10000` bench-Duraludon-energy
   priority now requires the attached card to actually be Metal Energy (`cid == METAL_ENERGY`),
   not just any card landing on a benched Duraludon.
4. **`score_attach`'s Hero's Cape branch** -- the Duraludon `8000` case now requires the
   target to be the Active Pokemon (`opt.inPlayArea == AreaType.ACTIVE`), not any Duraludon in
   play. Note: the donor writes bare `opt.inPlayArea` here; this file uses
   `getattr(opt, 'inPlayArea', None)` instead, matching this file's own defensive idiom used
   elsewhere (e.g. `apply_overrides`). This is a deliberate hardening of the donor snippet,
   not a transcription error.

## Guard restorations (base guards lucifer19 dropped)

5. **`all_my_pokemon`** -- restored the `or []` None-fallback on `ps.active`/`ps.bench` that
   base had and lucifer19 silently dropped.
6. **`detect_matchup`** -- restored the same `or []` None-fallback on `opp.active`/`opp.bench`.
7. **`agent()`'s crash fallback** -- restored `minCount` enforcement
   (`k = min(max(min_count, max_count), n)`). lucifer19's version clamped only against
   `maxCount`, so a crash on a `minCount > 0` prompt under-filled the selection. Kept
   lucifer19's determinism (`range(k)`) rather than reintroducing base's `random.sample`.

## Verification

- `python3 -m py_compile submissions/lucifer19_lossfix_merge/main.py` -- clean.
- `python3 src/test_lucifer_variants.py` -- 13/13 checks pass, self-contained mocks built
  from the real `cg.api` dataclasses bundled with this submission (no captured fixtures
  needed).
- Every helper function `_boss_has_lethal` depends on (`active_pokemon`,
  `opp_active_pokemon`, `opp_bench_pokemon`, `energy_count`, `retreat_cost`, `has_tool`,
  `prize_value`, `effective_damage`, `archaludon_ex_attack_route`,
  `planned_archaludon_attacks`) already existed in lucifer19's namespace -- no missing
  dependency risk.

## Local rating caveat

Local `ladder_eval.py` is documented to fail exactly this kind of within-archetype tweak
(`evaluation-methodology.md:355-360`: gaps of +4.2 and -12.4 mu measured where the real
ladder separated known pairs by 50.1 and 63.4). Local rating on this variant is a
crash/regression veto only -- promotion is decided on the real ladder.
