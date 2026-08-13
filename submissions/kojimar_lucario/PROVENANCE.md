# Provenance

Source: two public Kaggle kernels with near-identical content, same Mega Lucario agent:

- `kaggle.com/code/makthanithin/pokemon-tcg-ai-battle-1084-5-baseline` (title claims 1084.5)
- `kaggle.com/code/kojimar/...` (exact URL not re-verified at promotion time)

The shipped bytes here are **kojimar's** copy, not makthanithin's: makthanithin's published
`main.py` has a stray `) hi:` at line 322 and does not compile with `py_compile`. kojimar's
copy is clean and is what this directory ships.

Cleared under the 2026-08-13 third-party code decision: agents derived from public Kaggle
kernels may be submitted (they derive from the host's own permitted sample). This candidate
was previously local-eval-only under `submissions/_localonly_makthanithin_lucario/` with a
`DO-NOT-SHIP.md` guard; that guard is lifted by the policy change and this directory is the
promoted, shippable copy.

Never measured on the real ladder before this submission. Local frozen-panel mu 649.2
(pre-tau-fix estimator; not yet re-measured at tau=0).
