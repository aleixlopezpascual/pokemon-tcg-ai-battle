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
- **Only the 2 most recent submissions actually keep receiving episodes.** A third upload does not
  add a third runner — it starves the oldest of the three, whose μ then freezes wherever it was.
  Older submissions still *display* a μ on the leaderboard; that is not the same as accumulating
  games, and confusing the two cost a whole experiment arm on 2026-08-09. So **concurrency of 2,
  not the 5/day quota, is what limits experiment design**: every A/B is at most two arms wide, a
  control must be one of the two, and multi-arm designs run as sequential pairs. Upload the arm
  whose reading matters most *last*.
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
  `ladder_eval.py` (frozen-panel TrueSkill rating — **the ranking gate**),
  `trueskill_lite.py` + `test_trueskill_lite.py` (stdlib no-draw TrueSkill and its tests),
  `calibration_tracker.py` (local μ vs settled ladder μ, Spearman with bootstrap CI),
  `adversarial_validation.py` (IL covariate-shift test and panel-representativeness),
  `local_eval.py` (older pooled win-rate harness, superseded for ranking — see below).
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

## Local evaluation — `ladder_eval.py` is the gate, `local_eval.py` is not

**Rank candidates with `src/ladder_eval.py`, not `src/local_eval.py`.** Full derivation and every
measurement behind this is in `notebooks/kaggle-research/evaluation-methodology.md`'s
"2026-08-09 evaluation-harness rebuild" section; the operational summary:

```bash
python3 src/ladder_eval.py rate --candidate submissions/<name> --games 4000 --workers 8 \
    --json data/processed/ratings/<name>.json
```

It rates the candidate against a **frozen** 7-agent panel (`data/processed/panel_ratings.json`,
current version `fa733a4e989a`) using a pure-Python no-draw TrueSkill (`src/trueskill_lite.py`)
with Kaggle's parameterization, and reports local μ plus per-opponent Wilson CIs. Panel ratings
are fit once and **never refit** when evaluating a candidate — that is what makes μ comparable
across candidates, and what fixes `local_eval.py:136`'s self-exclusion bias (it drops the
candidate from its own roster, so roster members face an easier field than non-members).

`local_eval.py`'s pooled win rate is superseded **for ranking**. Keep using it for its
loss-tracing (`--save-losses`, `--repeats`), which `ladder_eval.py` does not duplicate.

Things that will otherwise be re-derived the hard way:

- **The gate ranks candidates, not one-line tweaks within one archetype.** Retro-validated
  2026-08-09 against the two pairs whose ladder answer was already known: frozen-panel μ separated
  them by 4.2 and −12.4 μ where the ladder separated them by 50.1 and 63.4, i.e. "tie" both times,
  and the sign was wrong on one. A mirror head-to-head (4000 battles) and pooled WR agree it is a
  tie. Choose within-archetype changes by mechanism from reading the code, and settle them on the
  ladder. Full writeup in `evaluation-methodology.md`'s "2026-08-09 retro-validation" section.
- **Measure a branch's reachability before crediting or blaming it.** The Archaludon
  `detect_matchup` guard was treated as a −63 μ regression while firing in 0/29,064 sampled
  states. Instrument the branch and count the share of *battles* in which it fires at least once.
- **Differences under ~25 μ are noise.** Two independent 24,000-game runs of the same candidate
  moved ~12 μ against a nominal σ of ~20.
- **No seed control exists** — `libcg.so` self-seeds from `std::random_device` and exports no
  seeding entry point, so Common Random Numbers is impossible. Sample size is the only lever.
- **Workers must be processes, not threads** — the engine is a ctypes singleton with a
  process-global `Battle.battle_ptr`.
- **`ladder_eval.py` pins `OMP_NUM_THREADS` and friends to 1 at module top, before numpy is
  imported.** Do not move or remove this. `il_agent_v2b` pulls in a threaded BLAS, and
  unpinned it cost 24.3 s CPU per battle (54× more than pinned) and made 8 workers run 2.8×
  *slower* than serial.
- **Agents can shadow each other's helper modules.** Four IL submissions each ship their own
  `il_features.py`; in one process the first to load wins `sys.modules` and later agents silently
  get the wrong helper. `ladder_eval._load_agent_isolated` handles it. If you write a new harness
  that loads multiple `main.py` files into one process, you need the same guard.

Calibration against the real ladder (`src/calibration_tracker.py`, `data/processed/calibration.csv`):
frozen-panel μ correlates with settled ladder μ at ρ = +0.80 vs pooled WR's +0.60 — but n=5, the
CI is [+0.11, +1.00], and p = 0.133. **The frozen panel is better-founded, not yet demonstrably
predictive.** Only a real submission settles a close call. Also note a hard ceiling on any
panel-based metric: 44.3% of the real field's decks are <0.30 Jaccard-similar to *any* panel deck.

## Open experiment: the fix-regression pattern (2026-08-09)

Two locally-clean fixes each scored ~50-63 μ *below* the version they fixed. Three arms are live
to find out whether that is real or noise, with decision rules written down before the readings
(see `10-day-plan.md`'s "2026-08-09 — fix-regression experiment" section). Three arms went up, but
only two run at a time, so the noise-control arm `55371582` was starved and measured nothing. Live
and valid: `55371585` and `55371590`, two one-line Dragapult arms isolating the two mechanisms,
both started within 6 seconds of each other against the same field. First readings at 6.5h (not
settled, do not act on them): B1 665.6, B2 557.5, and C exactly 600.0 — μ0, confirming it played
zero episodes. The B1−B2 gap of 108 μ points the opposite way to the hypothesis, i.e. the
collateral `hand_score` consumers B2 removed appear to have been helping. Read again at ~08-11,
≥2 readings ≥24h apart. The noise floor is still unmeasured, and the revised design for it is **two
byte-identical tarballs uploaded back to back** so they run as a simultaneous pair — better than
the original re-upload, which would have compared against a weeks-old reading. **Do not spend
slots on further one-line tweaks until the noise floor is known.**

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

The strongest remaining hypothesis — imitation-learning covariate shift — was tested on 2026-08-09
and **is not supported**. `adversarial_validation.py --mode il` separates IL self-play states from
the training corpus at AUC 0.979, but a *non-IL* control agent harvested against the identical
panel separates at 0.998 — higher. The separation is the local panel differing from the real
ladder field, not the IL policy's own trajectory, so DAgger does not follow from it. Every
frozen-panel μ also puts all four IL variants below every rule-based candidate (v2 565.2, v2b
532.2, v3 499.9, v1 446.0, vs Archaludon 689.9).

Two more candidates audited and added to the local-eval roster but **not submitted** —
`aristophanivan_probablity_v2` (real badge 933.8, local pooled 59.7%) and
`biohack44_alakazam_dunsparce` (Profile B) — both lose locally to Archaludon/Crustle, so neither
is worth a submission slot right now.
