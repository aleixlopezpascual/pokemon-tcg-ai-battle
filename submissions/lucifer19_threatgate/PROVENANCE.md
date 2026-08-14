# Provenance

Base: `submissions/lucifer19_lossfix_merge` (Variant A), unmodified fork -- see that
directory's `PROVENANCE.md` for the lucifer19/archaludon_lossfix lineage below it.

Variant B stacks on Variant A rather than branching from lucifer19 directly. Rationale: the
real-ladder noise floor is 50-65 mu and this repo's own measured within-archetype effects
have been as small as +1.8 mu (`archaludon_lossfix`'s matched-field reading) -- there is no
measurement budget to ablate changes one at a time. Each arm carries every change believed
positive so a single aggregate effect has a chance of clearing the floor.

## What changed

`opp_max_damage(obs)` (defined in the source kernel at what is now `main.py:441-454`) computes
a per-matchup incoming-damage ceiling and had zero call sites -- dead code since the kernel
was written. This variant wires it up as a threat gate:

1. **`_active_dies_next_turn(obs)`** (new function, inserted immediately after
   `opp_max_damage`) -- true iff the opponent's damage ceiling meets or exceeds the Active's
   remaining HP. Swallows any exception from `opp_max_damage` (which walks the opponent board
   and discard via `_estimate_alakazam`) and degrades to "no threat detected" rather than
   letting a raise there poison the scorer and drop the agent into its crash fallback.

2. **`score_retreat`** -- new branch: if the Active dies next turn, its retreat is affordable
   (`retreat_cost(active) <= energy_count(active)`), and a bench Pokemon would survive the
   ceiling, score `6000` for retreating to it. Placed after the existing `13000`
   attack-ready-retreat rule and before the `-100` default, so an offensive retreat still
   always wins and the new branch never pre-empts developing the board (still below the
   14000-28000 play/evolve range).

3. **`attach_target_score`** -- new penalty: if the Active dies next turn, the attach target
   *is* the Active, and it has fewer than 2 energy, subtract `4000`. Guarded on
   `energy_count(target) < 2` so the 2-to-3 attach that enables an attack this turn (the
   ramp's own high-score branch) stays reachable.

## Semantics confirmed before writing any comparison

`Pokemon.hp` in `cg/api.py` is documented "Current HP" (remaining), not max HP --
consistent with this file's own existing KO idiom (`effective_damage(dmg, target) >=
target.hp` in `_boss_has_lethal` and `planned_archaludon_attacks`). No inversion risk; no
need to dispatch a game-engine read for this.

## Verification

- `python3 -m py_compile submissions/lucifer19_threatgate/main.py` -- clean.
- `python3 src/test_lucifer_variants.py` -- 22/22 checks pass (13 from Variant A re-run
  against this module's namespace + 9 new threat-gate cases), including: the offensive
  retreat still dominates a simultaneous lethal threat, the bench-absorb branch requires
  an actual surviving bench Pokemon, and the attach penalty does not fire at
  `energy_count == 2`.

## Local rating caveat

Same as Variant A: local `ladder_eval.py` is a crash/regression veto only, not a promotion
signal, on this kind of within-archetype tweak (`evaluation-methodology.md:355-360`).
