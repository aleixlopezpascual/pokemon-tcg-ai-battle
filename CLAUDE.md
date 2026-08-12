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
  latency that a genuinely open question could use instead. See the "fix-regression pattern"
  section below for why this changed.

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

## Closed experiment: the fix-regression pattern (2026-08-09, resolved 2026-08-10)

Two locally-clean fixes each scored ~50-63 μ *below* the version they fixed. Three arms went up to
test whether that was real or noise; only two run at a time (see the concurrency rule above), so
the noise-control arm `55371582` was starved at μ0=600, measuring nothing. `55371585` (B1) and
`55371590` (B2), the two live Dragapult arms, settled with B1 ahead of B2 by a shrinking-but-
consistent gap (108 μ at 6.5h, 57.6 μ at 13h/24h+) — both still below the pre-split fix
(`55336268`, 688.0), same size as the noise already measured elsewhere (63.4 μ, 30.9 μ). **Never
resolved cleanly**: the planned identical-pair noise-floor measurement (two byte-identical
tarballs uploaded back to back) was never run — `probablity_v2` and `alakazam_dunsparce` took the
freed slots first (see Current Status). **Explicit policy change adopted instead (2026-08-10):
act on first readings, don't insist on ≥2 readings ≥24h apart before deciding.** With 6 days left
and concurrency-of-2 as the real bottleneck, waiting out a question already reasonably answered
costs an hour that could get a first read on a genuinely open one. The Dragapult B1/B2 track was
parked as-is on `55336268` (688.0), no mechanism adopted — see `10-day-plan.md`'s "2026-08-10 —
`probablity_v2` pre-flighted early" section for the full close-out.

## Current status (2026-08-12, see `10-day-plan.md` for live detail)

**The search/IL/heuristic-improvement track is closed.** Five separate mechanisms have now been
tried on top of the rule-based Archaludon baseline, and every one landed at parity or worse on the
pre-registered pooled-win-rate gate (≥47.0% vs a 41.9% baseline, three-matchup panel):

1. PIMC forward-search override (Orbit Wars-derived, `search_begin`/`search_step`) — mirror gate
   dead heat (49.7-53.3%), override rate only ~0.8% of decisions. Not shipped.
2. Same PIMC layer re-measured off-mirror (diagnostic gate G1) — confirmed a structural opponent-
   model defect (`score_attach` can't score an ATTACH above `END` for any non-mirror archetype,
   since none of their decks carry `METAL_ENERGY`), but even after fixing what could be fixed,
   pooled win rate came back at baseline (41.9%, +0.0pp). FAIL.
3. IL intent classifier contingency (Task 14) predicting the search layer's own intent labels —
   pooled 39.0% (**worse** than doing nothing), mirror regressed 13.7pp. FAIL, worse than #2.
4. Hidden-info visibility fix (energy/tool/preEvolution) — pooled 37.2%, the worst of all five
   attempts, mirror regressed 16.9pp. Root-caused to PIMC's own near-zero-draw noise-driven
   overrides, a pre-existing defect this attempt didn't touch. FAIL.
5. PIMC noise-driven-override fix (raised margin, added a minimum-draw floor) — recovered to
   parity (pooled 42.5%, +0.6pp, no regression on any matchup) but still short of the +5pp bar.
   Root-caused further: the mechanism only ever fires on ~25% of eligible decisions and only ~12%
   of those survive the confirmation gate — net ~3% of decisions change, a signal too small to
   separate from noise at n=1000/matchup. **This is the ceiling of the mechanism as built, not a
   tunable defect** — see `10-day-plan.md`'s "root-causing why the fifth attempt landed at parity".
6. A sixth, different-mechanism attempt (PIMC-oracle blunder finder: play the *unmodified*
   heuristic, use the oracle read-only to find and fix concrete decision bugs) found and fixed 3
   real bugs in a fork (`submissions/archaludon_lossfix/`, gitignored) but still landed at parity
   on the full 7-agent frozen-panel gate (μ=662.5 vs reference 676.3, diff −13.8). A manual loss
   trace afterward found one more real pattern (Alakazam/Dunsparce's Boss's-Orders-forced-switch
   into hand-size-scaling damage) but it's opponent-controlled and structurally unfixable at the
   candidate's own decision level. Not shipped.

**No untried mechanism remains** in the intent-PIMC/IL-classifier/blunder-finder family. Every
lever the `orbit-wars-teardown.md` research and this project's own diagnostics surfaced has been
built and gated. The one genuinely untried idea (IL filtered by rating *and* behavior, with a
shrunk label space matching a simplified action space — see `orbit-wars-teardown.md`'s "2nd place"
notes) was explicitly parked for the Strategy track (`pokemon-tcg-ai-battle-challenge-strategy`,
deadline 09-13), not this deadline, since it needs a redesigned label space, not a data/feature
bolt-on.

**Recommendation carried forward from 2026-08-11: ship the best rule-based candidate as the
Final Submission fallback and treat remaining runway as candidate selection, not further
mechanism development**, unless a genuinely new (not PIMC-margin-retuning, not more IL data)
approach is proposed.

### Submission landscape (real Kaggle scores, `kaggle competitions submissions` as of 2026-08-12)

| candidate | best/most recent real reading(s) | notes |
|---|---|---|
| `masamikobayashi_archaludon_cinderace` (Archaludon ex/Cinderace, hardened) | 643.1 → 774.8 → 811.4 → 711.4 → 680.5 (frozen since 2026-08-09, no submission since) | Highest peak reading of any candidate (811.4); noisy (±60-130 μ across readings on unchanged or near-identical code). Guaranteed fallback / de-facto 1st Final Submission. |
| `soutasakurai_libraryout_crustle` | 553.8 (stale, pre code-change) → 686.7 → **746.9** (2026-08-10/11) | Local μ improved to 685.7 after a 2026-08-07 code fix; real score followed. **Highest current real score of any candidate.** One currently-live slot. |
| `biohack44_alakazam_dunsparce` (Profile B) | 720.4 → 712.4 → **698.2** (drifting down) | Debut above local estimate (669.9) and above Archaludon's then-current reading. Other currently-live slot. |
| `aristophanivan_probablity_v2` | 711.7 → **659.4** (52.3 μ single-submission swing) | Self-reported badge 933.8 not replicated; real score is mid-pack. Not currently in the live pair. |
| `kiyota_dragapult_ex` | 703.5 → 727.3 → 738.1 (raw) / 688.0 (bench-fix) / 646.2 (B1) / 588.6 (B2) | Fix-regression track closed at parity/worse (see above); parked as-is on the 688.0 bench-fix version, no further work planned. |
| `archaludon_lossfix` (3 verified bug fixes, gitignored fork) | not submitted — local gate only, μ=662.5 vs 676.3 reference (parity) | On disk, available, deliberately never spent a slot since it didn't clear parity. |
| `archaludon_intent` / `archaludon_search` (PIMC/IL search layers) | not submitted | Closed negative results (see the 6-attempt list above); kept for reference, not slot-worthy. |
| `il_agent_v2`/`v2b`/`v3` (imitation learning) | 523.1-538.7 real; v3 never submitted (30.3% pooled, below v2) | Frozen twice now; see `baseline-comparison.md`. |

**Important for the 08-16 Final Submission decision: the two currently-live/accumulating slots
are `55416420` (crustle, 746.9) and `55409986` (alakazam_dunsparce, 698.2) — not Archaludon**,
whose 680.5 reading is frozen and will not move again unless resubmitted. If Archaludon is to be
one of the 2 manually-selected Final Submissions (per the guaranteed-fallback plan above), it
needs a fresh submission before 08-16 to get a live reading in the same window as its competitors,
since a frozen 6-day-old μ isn't directly comparable to two actively-accumulating ones. Crustle
(746.9) is currently the strongest real-scored candidate seen in this project's history.
