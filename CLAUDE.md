# CLAUDE.md

Working conventions for the PTCG AI Battle Kaggle competition repo, established over the first
2 days of work (2026-08-06/07). Read `notebooks/kaggle-research/*.md` for the actual research
findings — this file is about *how to work in this repo*, not what we've learned about the game.

## Competition shape

- Simulation ladder (`pokemon-tcg-ai-battle`), deadline **2026-08-16**. A separate Strategy
  track (`pokemon-tcg-ai-battle-challenge-strategy`, deadline 09-13) exists but is out of scope
  until after the Simulation deadline (deliberate decision, not an oversight).
- Submission = `main.py` (exposes `agent(obs_dict) -> list[int]`) + `deck.csv` (60 card IDs) +
  the competition's `cg` engine, packaged as `submission.tar.gz`, uploaded via
  `kaggle competitions submit` directly (not a kernel-linked code competition).
- Scoring: TrueSkill-style N(μ, σ²), moves on win/loss/draw only per episode — margin/speed
  don't matter. **First reading is noise; wait 24-48 hours and ≥2 readings before trusting a
  score** (same-agent resubmissions have landed 300+ points apart on day-1 readings — this is a
  documented platform characteristic, not something specific to our agents).

## Submission discipline

- **5 uploads/team/day.** ERRORed submissions (validation failure before any games run) do
  **not** count against this cap — confirmed empirically (see `10-day-plan.md` submission log).
- **The day boundary is UTC midnight, not local date.** Confirmed 2026-08-07/08: a submission
  made after local midnight still consumed "08-07"'s quota because UTC hadn't rolled over yet.
  Check the CLI's actual "N submissions remaining" message, don't assume a fresh 5 just because
  the local calendar date changed.
- Only **2 Final Submissions** count for placement, and they must be **manually selected** on
  Kaggle — auto-select picks your latest two uploads, not your best two. Do this deliberately
  near the 08-16 deadline, not by accident.
- Before every submission: tar-validate required files present
  (`{"main.py", "deck.csv", "cg/api.py", "cg/libcg.so"}`) and `py_compile` the main.py for a free
  syntax check. Both patterns adopted from audited public kernels, now standard practice here.
- Log every submission (ref, description, real score once known) in
  `notebooks/kaggle-research/10-day-plan.md`'s submission log table.

## The sandbox almost certainly has no numpy/pandas/scikit-learn/joblib

Confirmed by direct evidence: `il_agent_v2`'s first attempt (a scikit-learn
`HistGradientBoostingClassifier` scorer) ERRORed on real submission despite running perfectly
locally, on the extracted tar, and via `run-battle`/`local_eval.py` — the only difference from
every other (successful) submission here is that it was the first to need anything beyond
stdlib + the compiled `cg` engine. The Kaggle *simulation* sandbox is very likely more minimal
than the interactive notebook environment the discussion threads describe (`#708810`) — don't
assume the data-science stack is present just because a normal Kaggle notebook has it.

**If a trained model is genuinely needed**: export its decision logic to a dependency-free
format rather than pickling the library object. Pattern used successfully here (`il_agent_v2`
retry): `src/export_pure_predictor.py` dumps a `HistGradientBoostingClassifier`'s tree
structure to plain JSON, and `src/pure_predictor.py` re-implements the decision function using
only `json`+`math` — validated bit-for-bit identical to sklearn's own `predict_proba` before
shipping. **Verify any such submission by stripping site-packages from `sys.path` and
confirming it still imports and runs a full battle** — that's the actual test that would have
caught the first ERROR before spending a submission on it.

## The `exec()`-without-`__file__` gotcha

Kaggle runs the submitted `main.py` via `exec()` — **`__file__` is not defined in that scope.**
Any code that does `os.path.dirname(os.path.abspath(__file__))` will `NameError` on the real
submission even though it works fine in local testing (where `run-battle`/`local_eval.py` load
`main.py` via `importlib`, where `__file__` *is* available). This caused a real submission
ERROR early on (ref `55307378`).

The safe pattern (used everywhere after that): try the real Kaggle sandbox path first, and only
fall back to a `__file__`-based lookup inside a `try/except NameError` for local-test
compatibility:

```python
file_path = "deck.csv"
if not os.path.exists(file_path):
    file_path = "/kaggle_simulations/agent/deck.csv"  # real Kaggle sandbox path
if not os.path.exists(file_path):
    try:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deck.csv")
    except NameError:
        pass
```

Every well-engineered public kernel audited independently arrived at the same guard — this is a
known, common community gotcha, not a one-off bug.

## Repo layout

- `notebooks/kaggle-research/*.md` — all research findings, committed. `pulled/` subdirectory
  (gitignored) holds raw third-party kernel/notebook downloads for local audit only — never
  commit those, only our own notes about them.
  - `10-day-plan.md` — the day-by-day roadmap and submission log (source of truth for "what's
    the current plan and what's been submitted").
  - `baseline-comparison.md` — why the current baseline archetype was chosen, evidence trail.
  - `notebook-audit-template.md` — per-kernel audit entries.
  - `top-scores-report.md` — Code-tab/kernel score research.
  - `discussion-intel-report.md` — Discussion-forum research (204 topics indexed via
    `kaggle competitions topics list/show`, not manual browsing — see below).
  - `evaluation-methodology.md` — how local win-rate evaluation is designed and calibrated.
  - `prioritization-matrix.md` — candidate/task prioritization scoring.
- `src/` — reusable scripts: `fetch_kaggle_kernels.py` (list/pull public kernels),
  `local_eval.py` (multi-opponent local win-rate harness, see calibration caveat below).
- `submissions/<name>/` — one directory per candidate agent (gitignored — third-party-derived
  code and compiled engine binaries, not ours to commit). Each has `main.py`, `deck.csv`, and
  (after packaging) `submission.tar.gz`.
- `.claude/skills/` — `run-battle` (single-opponent local battle simulation),
  `secrets-and-data-guard` (pre-push scan, run before every push — this repo is private now but
  will go public later), `kaggle-competition-playbook` (Kaggle-specific workflow guidance,
  curated for this competition's shape).
- `.claude/agents/` — `game-engine-analyst.md`, the specialist for "what does this Observation
  field actually mean" questions (reads `cg/api.py`/`game.py`/`sim.py` directly rather than
  guessing); `secrets-scanner.md`, run proactively before any push or visibility change.

## Discussion-forum access (solved, don't re-derive)

The Discussion tab is a JS-rendered SPA — `WebFetch` returns nothing useful. But the **Kaggle
CLI's `topics` subcommand works and is authenticated/structured**:
- `kaggle competitions topics list <slug> --format json` — paginated (`--page-token`, printed
  as trailing text after the JSON array — strip before parsing). Loop until an empty page.
- `kaggle competitions topics show <id> --format json` — full comment tree for one topic. Does
  **not** return the original post body, only comments (usually enough to reconstruct it).
- Rate-limits (`429`) on bulk pulls — retry with backoff, don't treat one as unavailable.

## Local evaluation — what it can and can't tell you

`python src/local_eval.py --candidate submissions/<name>` pools win rate across a fixed 7-agent
roster (random baseline + rule-based submissions `kiyota_mega_lucario_ex`,
`masamikobayashi_archaludon_cinderace`, `soutasakurai_libraryout_crustle` + imitation-learning
agent `il_agent_v2b` + newer candidates `aristophanivan_probablity_v2`,
`biohack44_alakazam_dunsparce`) with Wilson 95% confidence intervals.
**Calibrated against real ladder scores and found to correctly flag obviously-weak candidates,
but it inverts fine-grained rankings between comparable-strength ones** (see
`baseline-comparison.md`'s calibration table). Use it as a pre-submission sanity gate, not a
way to pick a winner between two candidates that both look decent locally — only a real
submission answers that with confidence here.

## Current status (2026-08-08, see `10-day-plan.md` for live detail)

Two rule-based candidates in play, both real-scored and both ahead of anything IL has produced:
`submissions/masamikobayashi_archaludon_cinderace/` (Archaludon ex/Cinderace, hardened across two
passes, settled ~711-811) and `submissions/kiyota_dragapult_ex/` (Dragapult ex, 703.5/727.3,
`Fezandipiti_ex` empty-bench fix submitted `55336268`, pending its 2nd reading). Archaludon stays
the guaranteed fallback / one of the 2 eventual Final Submissions regardless of what else happens.

**IL track frozen (again).** Two real attempts now: v2 real-scored 523.1/531.8 (well below
rule-based); a scaled-up v3 push (more/ELO-weighted data, several new features, a guardrail
layer, a duplicate-option label fix) passed its offline accuracy gate comfortably but scored only
30.3% pooled in local eval — worse than v2, and clearly traced to the v3 retrain itself, not a
pipeline bug (both independently verified clean). Decided not to spend a submission on it and to
stop iterating on IL for now — see `baseline-comparison.md`'s "IL agent v3" section for the full
diagnosis. This is the second time IL has underperformed rule-based here; treat any future IL
pitch with real skepticism unless it comes with a concrete, verified fix for *why* the last two
attempts underperformed, not just more data/features in the same shape.

Two more candidates audited and added to the local-eval roster but **not submitted** —
`aristophanivan_probablity_v2` (real badge 933.8, local pooled 59.7%) and
`biohack44_alakazam_dunsparce` (Profile B) — both lose locally to Archaludon/Crustle, so neither
is worth a submission slot right now.
