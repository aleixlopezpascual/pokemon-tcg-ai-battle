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
  don't matter. First reading is noisy (same-agent resubmissions have landed 300+ points apart on
  day-1 readings — a documented platform characteristic, not something specific to our agents),
  and the measured between-submission noise floor is ~25-65 μ. **Policy since 2026-08-10: act on
  first readings rather than waiting for ≥2 readings ≥24h apart** — with concurrency-of-2 as the
  real bottleneck, waiting out an already-reasonably-answered question costs a slot's worth of
  latency that a genuinely open question could use instead. See
  `notebooks/kaggle-research/10-day-plan.md`'s 2026-08-10 entry for why this changed.

## Submission discipline

- **5 uploads/team/day.** ERRORed submissions (validation failure before any games run) do
  **not** count against this cap — confirmed empirically (see `10-day-plan.md` submission log).
- **The day boundary is UTC midnight, not local date.** Confirmed 2026-08-07/08: a submission
  made after local midnight still consumed "08-07"'s quota because UTC hadn't rolled over yet.
  Check the CLI's actual "N submissions remaining" message, don't assume a fresh 5 just because
  the local calendar date changed.
- **Only the 2 most recent submissions actually keep receiving episodes.** A third upload does not
  add a third runner — it starves the oldest of the three, whose μ then freezes wherever it was.
  Older submissions still *display* a μ on the leaderboard; that is not the same as accumulating
  games, and confusing the two cost a whole experiment arm on 2026-08-09. So **concurrency of 2,
  not the 5/day quota, is what limits experiment design**: every A/B is at most two arms wide, a
  control must be one of the two, and multi-arm designs run as sequential pairs. Upload the arm
  whose reading matters most *last*.
- Only **2 Final Submissions** count for placement, and **there is no manual selection in this
  competition** — corrected 2026-08-15 per direct user confirmation, overriding this doc's
  earlier (wrong) claim that Finals are manually picked in the Kaggle UI. Whichever 2 submissions
  are the most recently uploaded *at the deadline* are automatically what gets sent and scored.
  The only lever is **upload order/timing**: to swap out a weak "latest" submission while keeping
  a good older one, re-upload the good one again *after* the replacement so it reclaims the
  newest slot — this costs 2 submission-quota slots and resets the re-uploaded candidate's
  episode count to zero.
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
  - `orbit-wars-teardown.md` — top-3 writeup mining from a different sim competition (Orbit
    Wars); the transferable finding was `cg/api.py`'s `search_begin`/`search_step` forward-sim
    API, which fed the PIMC search layer (built, evaluated, concluded negative — see
    `10-day-plan.md`).
- `src/` — reusable scripts: `fetch_kaggle_kernels.py` (list/pull public kernels),
  `ladder_eval.py` (frozen-panel TrueSkill rating — **the ranking gate**),
  `trueskill_lite.py` + `test_trueskill_lite.py` (stdlib no-draw TrueSkill and its tests),
  `calibration_tracker.py` (local μ vs settled ladder μ, Spearman with bootstrap CI),
  `adversarial_validation.py` (IL covariate-shift test and panel-representativeness),
  `local_eval.py` (older pooled win-rate harness, superseded for ranking — see below).
- `submissions/<name>/` — one directory per candidate agent. `main.py`/`deck.csv` — our own
  authored/modified logic — are tracked and committed (policy since 2026-08-12, after a
  `git worktree remove --force` silently deleted a real, verified fork — `archaludon_lossfix` —
  because it only ever existed as gitignored files inside that worktree; see CLAUDE.md's git
  history around that date). The compiled engine binary (`cg/`, ~5.2M/candidate, third-party) and
  build artifacts (`submission.tar.gz`, `__pycache__/`) stay gitignored to avoid repo bloat.
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

## Local evaluation

Ranking methodology, `ladder_eval.py` vs `local_eval.py`, and every hard-won pitfall (order
invariance, seed control, worker isolation, module shadowing) now lives in
`.claude/rules/evaluation.md` — it loads automatically when a session touches
`src/ladder_eval.py`, `src/trueskill_lite.py`, `src/local_eval.py`,
`src/calibration_tracker.py`, or `notebooks/kaggle-research/evaluation-methodology.md`.

## Current status

See `notebooks/kaggle-research/10-day-plan.md` for the live submission log, current candidate
standings, and day-by-day history — this file only covers repo conventions, not point-in-time
status.
