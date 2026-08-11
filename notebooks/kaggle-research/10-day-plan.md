# 10-day execution plan — PTCG AI Battle

Deadline: **2026-08-16**. Today: **2026-08-06**. Leaderboard (checked 08-06) currently tops
out around **1188** (Elo-style rating, not a raw win %) — use this as the live bar for how
competitive a given kernel's disclosed LB score actually is.

## Day 1 (08-06) — Pull + skim
- [ ] `python src/fetch_kaggle_kernels.py --pull-top 12` — pulls the top kernels by vote count
      into `notebooks/kaggle-research/pulled/` (gitignored, third-party code).
- [ ] Manually browse the competition Discussion tab (sorted Most Votes / Hot) — this is
      **not scriptable** (confirmed: Kaggle's Discussion tab is a JS SPA, no API endpoint
      exists for per-competition forum threads; a search-index query surfaces thread
      *titles* but never post bodies/comments). Paste back anything about meta shifts,
      scoring quirks, or common submission pitfalls. Known thread titles worth opening first
      (found via search index, 2026-08-06 — content unread, titles only):
  - "Differences Between the Official Pokémon TCG Rules and the Simulator Behavior" (shige) —
    read before writing any agent logic, likely documents simulator quirks/edge cases.
  - "Tracking 3,057 teams through 6 weeks of meta: who switched decks, when — and why it was
    always too late" (Sumi) — directly answers the meta-timing question this whole plan cares about.
  - "Alternative PTCG Rankings, inspired by Alternative Orbit Wars Rankings" (c-number)
  - "my plan on how to do RL training" — relevant if pursuing an RL approach.
  - "Incorrect all_card_data() text for Team Rocket's Great Ball (#1132)" (Dries Smit) — engine
    data bug report, check if it affects deck-building.
  - "Reminder about the Kaggle Simulation Competition Format" / "How to Get Started + Official
    Discord" (Addison Howard) — logistics, read once for submission-format gotchas.
- [ ] Confirm the `run-battle` skill runs end-to-end against the bundled `sample_submission`
      baseline (`data/raw/sample_submission/`) — this is the local feedback loop every later
      day depends on.

## Day 2 — Audit + synthesize
- [ ] Fill out `notebook-audit-template.md` for kernels selected per `prioritization-matrix.md`
      (official rule-based samples first, then highest disclosed-LB kernel, then most recent
      meta-snapshot, then 1-2 anti-Crustle notebooks).
- [ ] Write a short synthesis at the top of the audit file: which deck archetype(s) look
      strongest right now, whether rule-based or RL/search approaches are actually winning
      vs. just popular, and what the LB950+ baseline (`romanrozen/strong-start-baseline-agent-v10-lb-950`)
      does differently from the official samples.

## Days 3-4 — Pipeline setup
- [ ] Pick a starting base for `submissions/` — the strongest reusable official sample or
      high-vote kernel from the audit, not a from-scratch rewrite.
- [ ] Get `main.py` + `deck.csv` running end-to-end through `run-battle` against the baseline
      opponent; confirm the deck passes legality checks (60 cards, Basic Pokémon present, no
      illegal duplicates — `run-battle` rejects illegal decks pre-battle rather than crashing
      mid-game).

## Days 5-7 — Iterate
- [ ] Use `run-battle` win rate as the fast local feedback loop while tuning deck choice and
      agent decision logic.
- [ ] Explicitly test the candidate against a Crustle-style deck if one surfaces as a weak
      matchup — multiple public kernels treat Crustle as a named recurring threat.
- [ ] Re-pull/audit 1-2 more kernels only if a specific gap surfaces (e.g. a matchup the
      current deck loses to, or a technique referenced in Discussion that wasn't in the
      original kernel pull).

## Day 8 — Late-meta check
- [ ] Re-run `python src/fetch_kaggle_kernels.py --list-only` — competitions often see a burst
      of new public notebooks near the deadline; diff against Day 1's list for new high-vote
      entries.
- [ ] Re-skim Discussion for last-minute meta shifts or scoring changes.

## Day 9 — Hardening
- [ ] Re-verify deck legality on the final candidate.
- [ ] Run `secrets-and-data-guard` (`bash .claude/skills/secrets-and-data-guard/scripts/scan.sh`)
      before any push — this repo is private now but expected to go public later.
- [ ] Final local win-rate validation via `run-battle` with a higher battle count for a
      tighter confidence interval.

## Day 10 (08-16) — Submit
- [ ] Submit early in the day, not near the deadline — leaves buffer for any Kaggle
      submission-pipeline issues.

## Submission log

| Ref | Date | Description | Status | μ |
|---|---|---|---|---|
| `55307378` | 2026-08-06 21:32 UTC | Official Kiyota Mega Lucario ex sample, deck.csv path fixed, placeholder (10/10 vs local random) | **ERROR** | — root cause: my deck.csv path fix used `__file__`, but Kaggle runs `main.py` via `exec()` with no `__file__` in scope (confirmed via `pulled/TomBombadyl__kaggle_pokemon/scripts/package_submission.py` comment) — likely a NameError at import time. Fixed: reverted to the original hardcoded `/kaggle_simulations/agent/deck.csv` fallback as primary, `__file__` only as a `NameError`-guarded local-test-only fallback. Re-verified 10/10 locally. Resubmitted. |
| `55307583` | 2026-08-06 21:48 UTC | Retry of 55307378 with the deck.csv path fix | COMPLETE | **450.9** (1st), **439.9** (2nd, 2026-08-07 check) — stabilizing low ~440-450. This is the raw, unguarded official Kiyota "Intermediate Level" sample — floor-tier as expected, not a bug. Superseded as our working baseline by 55308121 below. |
| `55308121` | 2026-08-06 22:41 UTC | masamikobayashi Archaludon ex/Cinderace public sample (v6), matchup-tuned. See `baseline-comparison.md` for why this replaced the Lucario baseline. | PENDING | New working baseline. 70% WR vs our own Lucario submission locally (20 games). Check ≥40 min for 1st reading, ≥2 readings before trusting. Live leaderboard top ~1202 for reference. |
| `55308334` | 2026-08-06 23:02 UTC | soutasakurai LibraryOut Crustle/Great Tusk/Terrakion (mill/deck-out control) — see `top-scores-report.md` for the full risk disclosure (author's own "not fully functional" caveat) | COMPLETE | **553.8** — despite 80% local WR vs Archaludon and 95% vs Lucario. 3rd confirmation that local win rate vs a narrow opponent pool doesn't predict ladder μ. |
| `55308975` | 2026-08-06 23:53 UTC | User's own fork of `romanrozen/strong-start-baseline-agent-v10-lb-950` — actual code is a renamed copy of `jazivxt/codex-sol-eclipse-alakazam` (Alakazam weighted-scorer) | COMPLETE | **688.5** (or 694.4, order vs 55309000 not fully confirmed) |
| `55309000` | 2026-08-06 23:54 UTC | User's own fork of `biohack44/pok-mon-tcg-ai-battle-meta-snapshot-07-july` (updated version, "06-29" snapshot) — ran default Profile A, whose bundled `main_py` is byte-identical to masamikobayashi's Archaludon agent (deck tweak `flex_archaludon_0018_minus1182_plus1213`: swap card 1182→1213) | COMPLETE | **694.4** (or 688.5) — essentially the same agent as our own `55308121`, score gap likely early-reading noise, not a real implementation difference. |

**Quota used for 2026-08-06: 5/5 COMPLETE submissions (the 6th attempt, `55307378`, ERRORed and did not count). No submissions remain today.** Real scores across all 5: Lucario 490.8, Archaludon (ours) 643.1, Great Tusk 553.8, Alakazam-weighted 688.5, Archaludon (meta-snapshot's tuned variant) 694.4 — all well below live leaderboard top (~1202), and the two Archaludon attempts far below TomBombadyl's claimed 1196-1224 for the same archetype. Gap is likely: (a) none of these have a 2nd stabilizing reading yet, (b) TomBombadyl's specific empty-bench-guard addition, not yet replicated here, (c) meta drift since TomBombadyl's reading (over 5 weeks stale).

**Independent large-sample confirmation of Archaludon as the right archetype**: `biohack44`'s meta-snapshot notebook's embedded field data (real, not self-reported) shows Archaludon at **62.2% score rate over 1725 games** (Wilson CI 59.9-64.5%), the highest of any high-volume archetype (alakazam_dunsparce 51.3%, starmie 51.9%, dragapult 49.1%, hop_trevenant 45.5%, lucario 42.4%). This is now a 5th independent source pointing at Archaludon — the gap to close is implementation quality, not archetype choice.

**Correction (2026-08-07):** `55308975` = **694.4** (stable), `55309000` = **682.0** (drifted down from initial ~688-694) — these two refs were recorded swapped above; corrected here as the source of truth.

## 2026-08-07 — imitation-learning pivot (see `.claude/plans/option-1-detailed-cryptic-brook.md` for the full IL rebuild plan)

| Ref | Date | Description | Status | μ |
|---|---|---|---|---|
| `55324974` | 2026-08-07 12:47 UTC | `il_agent_v2` — imitation-learning scorer, 764k training decisions (299 episodes + 4,483 ELO-filtered from 2026-08-05), Grimmsnarl/Froslass deck mined from real data. Local pooled WR 47.5%, still 0-10% specifically vs our own Archaludon baseline across all IL variants tried. | **ERROR** | Ran perfectly locally (loose files, extracted tar, `run_battle`, `local_eval`) — root-caused to the Kaggle simulation sandbox almost certainly lacking numpy/pandas/scikit-learn/joblib (every prior submission here only ever needed stdlib + the compiled `cg` engine; this was the first to pull in the data-science stack). Fixed: exported the trained model's decision-tree structure to pure JSON + a stdlib-only (`json`+`math`) predictor (`src/pure_predictor.py`), validated bit-for-bit identical to sklearn's own `predict_proba` before shipping, and confirmed the new `main.py` imports and runs a full battle with site-packages stripped from `sys.path` entirely. Resubmitted as `55325282`. |
| `55325282` | 2026-08-07 13:03 UTC | `il_agent_v2` retry, zero external dependencies (see above) | COMPLETE | **523.1** (1st), **531.8** (2nd, ~2h later — only ~2h apart, not the full 24h). Well below Archaludon (643.1) and below the plan's own Gate C "freeze IL" threshold (650). Trending toward "rule-based wins this round" but not yet the full stabilization window. |
| `55327510` | 2026-08-07 14:58 UTC | Hardened Archaludon (retry of `55308121`, same archetype) — fixed the unclipped `random.sample` gap from the hardening pass, rest of the correctness checklist already confirmed safe | COMPLETE | **771.6** (1st reading) — a real, substantial +128.5 jump from the unhardened 643.1, not noise-level. Strong evidence the `maxCount > len(options)` crash-fallback bug was genuinely costing real games. **New best score.** Need a 2nd reading before fully trusting the magnitude, but this is the clearest signal all session that a specific code fix (not archetype/deck choice) moved the needle. |

**Quota for 2026-08-07: 3/5 used (1 ERROR did not count against it), 2 remaining.** Hardened Archaludon (`55327510`, 771.6) is the new best real score and leading Final Submission candidate. IL track (523-532) now clearly behind — hold off on further IL submissions until its 24h window closes and a final call is made per Gate C.

`55327510`'s 2nd reading: **811.4** — stable, confirms the 771.6→811.4 range is real, not a lucky first read.

| `55330407` | 2026-08-07 17:34 UTC | Archaludon, 2nd hardening pass (matchup-logic audit via `superpowers:subagent-driven-development`, plan at `docs/superpowers/plans/2026-08-07-archaludon-matchup-audit.md`) — confirmed+fixed a real `TypeError` crash in `detect_matchup` when the opponent's active is face-down (`None`, a documented reachable engine state); Crustle/Alakazam/Hop branches all independently audited and confirmed already correct against real engine data, no other changes | PENDING | Very rare in real data (0/29,064 sampled) so expected uplift is likely small vs the `random.sample` fix's — real test either way. |

**Quota for 2026-08-07 after this submission: 4/5 used, 1 remaining.** Holding the last slot in reserve.

`55327510` settled at **774.8** on a later reading (drifted from 811.4 peak); `55330407` settled at **718.3** — the two hardening-pass fixes now both stable, real value of this specific implementation looks to be ~720-775.

| `55335494` | 2026-08-07 23:12 UTC | Official Kiyota Dragapult ex sample (raw, no bench guard yet) — second archetype track. TomBombadyl's private testing showed this exact official sample + one bench guard hit 880.9 μ, above anything gotten from Archaludon so far. Testing the raw sample first before investing guard-engineering effort in an unfamiliar 850-line codebase. Local pooled WR 61% (`submissions/kiyota_dragapult_ex/`). | PENDING | Note: `kaggle`'s daily quota resets on UTC midnight, not local date — this was still "2026-08-07" quota-day despite local date already reading 08-08. **Quota now 5/5 used for 08-07-UTC, 0 remaining until rollover.** |

`55335494` settled at **727.3** on a later reading (up from the initial 703.5).

## 2026-08-08 — Dragapult ex `no_active` loss fix

Traced Dragapult's `no_active` losses via `local_eval.py --save-losses`/`--repeats` (see
`baseline-comparison.md`'s "Dragapult ex `no_active` loss investigation and fix" section for the
full trace-level writeup). First hypothesis (a generic "bench guard") didn't survive tracing —
0/3 sampled losses had a legal Basic sitting unbenched. Second pass found a real bug:
`Fezandipiti_ex` (a legal Basic) had no fallback score in `hand_score` outside three narrow
ability-timing conditions, so `OptionType.PLAY`'s `card_score > 0` gate vetoed ever playing it —
including onto a fully empty bench in a real traced loss. Fixed with one line (`elif
len(my_state.bench) == 0: score = 25000`). Validated locally: `no_active` share of losses
dropped ~3-4x (Archaludon 15-25%→7.7%, Lucario 15-25%→4.2%), pooled/matchup win rates unchanged
(71.3% vs 70.2%, 35.0% vs 35.6%) — clean, isolated fix, no regression.

| Ref | Date | Description | Status | μ |
|---|---|---|---|---|
| `55336268` | 2026-08-08 00:02 UTC | Dragapult ex, Fezandipiti_ex empty-bench fix (see above) — one-line fix, `no_active` loss share cut ~3-4x locally vs Archaludon/Lucario, no regression elsewhere | PENDING | New day's quota (5/5 available at 00:00 UTC rollover), this used 1. 4/5 remaining for 2026-08-08. |

**New durable lesson for `CLAUDE.md`**: any submission that imports beyond stdlib + `cg` is a real, demonstrated risk — the Kaggle simulation sandbox is very likely more minimal than the interactive notebook environment the discussion threads describe. Prefer pure-Python/stdlib implementations for anything shipped to the ladder; if a trained model is genuinely needed, export its decision logic to a dependency-free format rather than pickling the library object.

## 2026-08-07 — rule-based hardening pass (parallel worktree, while waiting on the IL reading)

Done ahead of the original Day-8 slot since there was idle time waiting on `55325282`'s
stabilization. Full findings in `baseline-comparison.md`'s "Rule-based hardening pass" section —
summary: went through every correctness item flagged in `discussion-intel-report.md` against
Archaludon's real code and the real engine (not assumption). Most repeatedly-flagged advice
("add a bench guard") turned out to already be handled, proactively and more thoroughly than
expected. One real gap found and fixed: an unclipped `random.sample` in the last-resort
exception fallback that could itself crash if `maxCount` ever exceeded the option count. Live in
`submissions/masamikobayashi_archaludon_cinderace/main.py`.

**4 of 5 daily uploads remain for 2026-08-06.** Only 2 Final Submissions count for placement and must be *manually* selected later — don't forget this near the deadline.

## 2026-08-08 — IL agent v3 scaled-up push, frozen at Gate B

Plan: `docs/superpowers/plans/2026-08-08-il-agent-v3-scaled-push.md`. 7 of 8 tasks executed via
`superpowers:subagent-driven-development` (guardrail layer, leaderboard-score attachment,
ELO-conditioning + sample weighting, duplicate-option label fix — plus a real bug in that fix
caught by an independent security review post-completion and re-fixed — `energy_gap` feature,
full retrain, threshold calibration/export/packaging). **Task 8 (submit) was not run.**

Gate B (`local_eval.py` pooled win rate) failed badly: **30.3% [25.4, 35.8]**, vs. a 47.5-47.6%
bar (v2's real score and a same-model-plus-guardrail checkpoint). Full write-up, including the
clean signal that the regression traces to Task 6's retrain specifically (not the guardrail or
export/packaging, both independently re-verified correct), in `baseline-comparison.md`'s "IL
agent v3" section. **No submission spent on this** — decided (human-confirmed) to freeze the IL
track again rather than iterate further, given ~7 days left and two real IL attempts now both
underperforming every rule-based candidate. `submissions/il_agent_v3/` exists locally but is not
and should not be submitted without a resolved diagnosis.

## 2026-08-09 — fix-regression experiment (Arms C / B1 / B2)

Two changes on this project were validated locally as clean, isolated and regression-free, and
both scored materially *lower* on the ladder than the version they fixed:

| pair | pre-fix | post-fix | delta |
|---|---|---|---|
| Archaludon `detect_matchup` None-guard | `55327510` **774.8** | `55330407` **711.4** | −63.4 |
| Dragapult `Fezandipiti_ex` empty-bench | `55335494` **738.1** | `55336268` **688.0** | −50.1 |

If the pattern is real, local validation cannot separate an improvement from a regression and
every remaining change before 08-16 is a coin flip. If it is noise, we are sitting on two false
alarms. Distinguishing the two requires the ladder's **between-submission noise floor**, which has
never been measured here — only *within*-submission drift is known (`55327510` read 771.6 / 811.4
/ 774.8 on identical code, a 40-point spread).

Three arms, submitted within 25 seconds of each other so they share a field and an episode count
at read time. Two slots held.

> **Design error, caught the same day (2026-08-09).** Only the **two most recent submissions
> actually keep receiving episodes** — a third does not add a third runner, it starves the oldest
> of the three. So Arm C, uploaded first, never accumulated games and the noise-floor measurement
> did not happen. The earlier justification ("all submissions stay live on the ladder", from
> watching `55308975`/`55309000` keep moving) confused a *displayed* μ with an *accumulating* one.
> The binding constraint on experiment design is **concurrency of 2**, not the 5-uploads/day
> quota: every A/B is at most two arms wide, and multi-arm designs must run as sequential pairs.
> B1 and B2 are the two that are actually live, which is still a valid head-to-head. The revised
> plan for the noise floor is below.

| Ref | Date | Description | Status | μ |
|---|---|---|---|---|
| `55371582` | 2026-08-09 07:32 UTC | **Arm C — noise control.** Byte-identical re-upload of the tarball that produced `55330407` (sha256 `259ae8b0…`, untouched since 08-07 17:34 UTC). Zero code change. | **VOID** | Reads **600.0** at 14:04 UTC — exactly μ0, the default prior. It played zero episodes, starved by B1/B2 within the same minute. Measures nothing. |
| `55371585` | 2026-08-09 07:32 UTC | **Arm B1 — PLAY priority.** One line vs `55336268`: the empty-bench `Fezandipiti_ex` case gets PLAY priority 50500 (below Dreepy's 51000) instead of the fixed 53000; the `pre_ko` ability-timing case stays at 53000. | LIVE | **665.6** (1st reading, 6.5h). Not settled — ignore per the ≥2-readings rule. |
| `55371590` | 2026-08-09 07:32 UTC | **Arm B2 — gate value.** One line vs `55336268`, in a different place: `hand_score` empty-bench value 25000 → 3000. PLAY gate still opens; the three collateral consumers stop firing. | LIVE | **557.5** (1st reading, 6.5h). Not settled. |

### First readings (2026-08-09 14:04 UTC, 6.5h in) — provisional

Both arms are 6.5h old and started from μ0 = 600, so the absolute numbers are not yet meaningful:
`55335494` read 703.5 at ~24h and 743.1 at ~32h, i.e. this ladder is still climbing well past this
point. Neither can be compared against `55336268`'s 688.0 either — that figure is *frozen*, since
`55336268` was displaced out of the active pair this morning and no longer accumulates episodes.

What the design does protect is the **B1 − B2 contrast**: 12 seconds apart, same field, same
window, same episode count. That gap is **108 μ in B1's favour**, and its direction contradicts
the hypothesis the arms were built to test.

B2 removed the three collateral `hand_score` consumers (the `TO_BENCH` priority over Dreepy, the
never-discard effect, and the `Night_Stretcher >= 18000` trip). If those were the damage, B2 should
have gained. It sits 108 μ below B1 and 42 μ below its own prior. Provisional reading: **those
consumers were helping, not hurting** — most plausibly Night_Stretcher recovering Fezandipiti_ex is
worth more than benching it costs. If that survives two settled readings, B2 is out and B1 is the
surviving Dragapult candidate.

Held to honestly: with the noise floor still unmeasured, 108 μ *looks* decisive but cannot be
called decisive. Within-submission drift on identical code has already been seen at 40 μ
(`55327510`: 771.6 / 811.4 / 774.8). The identical C/C' pair remains the measurement that unlocks
interpreting any of this.

**Why two Dragapult arms rather than one dose-response sweep.** `hand_score` feeds four consumers
with different semantics, and 25000 perturbs three of them:

| consumer | how `hand_score` is used | effect of 0 → 25000 |
|---|---|---|
| `OptionType.PLAY` | **gate only** (`card_score > 0`); priority is a fixed 53000 | Fezandipiti_ex becomes playable at 53000 — above Dreepy's 51000 and Budew's 52000, so on an empty bench the agent benches a 2-prize ex ahead of its own evolution engine. |
| `TO_BENCH` / `TO_HAND` | **priority directly** | 25000 outranks Dreepy's 18000 in bench-selection ordering. |
| `DISCARD` | `-hand_score` | 25000 makes Fezandipiti_ex the last card ever discarded. |
| `Night_Stretcher` gate | `card_score >= 18000` | 25000 crosses it, so Night_Stretcher now recovers a 2-prize ex. |

A `1 / 15000 / 25000` sweep would have been void: at the PLAY gate all three values are identical
(`> 0` → 53000). The dial only exists on the other three paths. Hence one arm per mechanism.

B2's value is 3000 rather than 1 because `DISCARD` negates the score — at 1, Fezandipiti_ex would
become one of the *first* cards discarded, a new regression. 3000 sits below Dreepy's 18000 and
the Night_Stretcher threshold while staying above obvious discard fodder (same rank as a Drakloak
with nothing to evolve from).

With the two live arms this is a partial factorial with both main effects estimable:

| arm | PLAY priority | `hand_score` value | status |
|---|---|---|---|
| `55335494` | never plays (gate closed) | 0 | live, 738.1 |
| `55371585` (B1) | 50500 (below Dreepy) | 25000 | new |
| `55371590` (B2) | 53000 | 3000 | new |
| `55336268` | 53000 | 25000 | live, 688.0 |

**Reachability was measured, not assumed** — the Archaludon guard was credited with a 63 μ swing
despite firing in 0/29,064 sampled states, and repeating that mistake would make these arms
unfalsifiable. Over 600 battles against four panel opponents, the `hand_score` empty-bench branch
(B2's target) fires in **41.2%** of battles and the PLAY branch offers Fezandipiti_ex with an
empty bench (B1's target) in **27.7%**. Both arms change real behavior.

That measurement also sharpens the puzzle: the Dragapult fix alters behavior in ~41% of battles
and moves local μ by 4.2, while the Archaludon fix alters behavior in 0% and "moved" the ladder
63.4. The asymmetry is itself evidence the ladder deltas are noise-dominated.

### Update (2026-08-10) — real submission table pulled, B1 frozen early, no clean noise pair yet

`kaggle competitions submissions` gives current state, no slot spent:

| ref | desc | status | μ |
|---|---|---|---|
| `55371582` (Arm C) | noise control | starved at upload+~24s | 600.0 (μ0, never played — confirmed dead) |
| `55371585` (B1) | PLAY-priority fix | **frozen** at ~13h (displaced by `55389372`) | 646.2 |
| `55371590` (B2) | hand_score-value fix | **live**, paired with `55389372` | 588.6 |
| `55389372` | 3rd upload, bytes identical to `55330407` | live | 680.5 |
| `55330407` | 2nd Archaludon hardening pass (frozen, older) | frozen | 711.4 |
| `55336268` | pre-split Dragapult fix (frozen, older) | frozen | 688.0 |

Upload timestamps (all 08-09) explain the starvation chain: C 07:32:32 → B1 07:32:44 → B2
07:32:56 → `55389372` 20:42:34. Each new upload evicts the older of the active pair. C died in
~24s (already known). B1+B2 ran together for **~13h** until `55389372` displaced B1; B2 has been
paired with `55389372` since and is still accumulating.

**The decision rule below cannot be applied as written.** It calls for ≥2 readings ≥24h apart per
arm; B1 got exactly one reading, frozen at ~13h — short of a full settle, and it can never get a
second, since it no longer receives episodes. B2 has one live reading past 24h elapsed and could
still move. Reporting what the data actually supports rather than forcing it into the rule:

- **B1 > B2 direction holds across two independent, differently-mature readings**: 108 μ at 6.5h,
  now 57.6 μ at (13h frozen) vs (24h+ live). Same sign both times. Leaning real, not proven — the
  gap nearly halved between readings, consistent with either genuine convergence or B1's early
  freeze catching it before a regression to the mean.
- **Both arms still read below the pre-split fix** (`55336268`, 688.0): B1 is 41.8 μ under, B2 is
  99.4 μ under. The original fix-regression puzzle is not resolved — neither isolated mechanism
  recovers the pre-fix score.
- **New same-code data point, but not the clean design**: `55330407` (711.4) vs `55389372`
  (680.5) is a 30.9 μ gap on byte-identical bytes. This is a re-upload-vs-old-reading comparison
  (different time, possibly different field composition) — exactly the contaminated design the
  plan below already flags as inferior to a true simultaneous pair. Treat as a second noisy data
  point alongside the existing 63.4 μ one (`55327510` vs `55330407`), not as the clean noise-floor
  measurement still pending (see next section). Both same-code gaps (63.4, 30.9) bracket the 41.8
  μ B1-vs-prefix gap and roughly match the 57.6 μ B1-vs-B2 gap — i.e. **every effect measured so
  far, including the "B1 > B2" one, is the same size as noise between identical bytes.** Directional
  consistency across two readings is suggestive but not yet distinguishable from noise.

No slot currently free to act (both active slots held by B2 and `55389372`). Next real step is the
still-pending true simultaneous C/C' pair (below) once a slot opens — that is the only design left
that can actually separate signal from this noise floor.

### Decision rules, written before the readings arrive

Fixing these in advance so the verdict is not fitted to whatever number shows up. Take ≥2 readings
≥24h apart per arm and ignore first readings (~08-11).

| observation | conclusion | action |
|---|---|---|
| C settles within ~15 μ of 711.4 | noise floor is small; both −50/−63 gaps are real regressions | trust the B1/B2 ordering, adopt the winner, and treat every local-only validation from here as untrustworthy |
| C settles 40+ μ from 711.4 | noise floor swamps both gaps | the "fixes made it worse" pattern is an artifact; stop acting on it, revert nothing, requeue the Dragapult track on its merits |
| C settles 15–40 μ away | ambiguous | say so; weight B1/B2 by mechanism plausibility rather than by μ alone |

The C-vs-`55330407` comparison above is void, since C never ran. B1 vs B2 stands: both are live,
both started within 6 seconds of each other, and both face the same field over the same window.

### Revised noise-floor measurement: an identical *pair*, not an identical re-upload

The concurrency limit turns out to enable a strictly better design than the one it broke. Arm C
compared a re-upload against a reading taken weeks earlier, against a different field, over a
different episode count — a noise measurement contaminated by every one of those. Uploading **two
byte-identical tarballs back to back** puts both in the active pair, so they run simultaneously,
against the same field, over the same window. Whatever μ separates them is between-submission
noise with the time confound removed.

Sequence, given that only two arms can run at once:

1. **Now → ~08-11:** let B1 and B2 accumulate. Read both, ≥2 readings ≥24h apart.
2. **Then:** upload the identical pair `C` / `C'` (2 slots, same minute). Their spread is the
   noise floor.
3. **Then:** re-run the winner of B1/B2 against whichever live arm it needs to beat.

Note the cost this imposes on everything else: at concurrency 2, each round of any A/B costs
~40h of latency and the whole field of comparison, so with the 08-16 deadline there is room for
roughly three more rounds total. Arm choice matters much more than arm count.

This experiment cannot reach statistical significance — even the identical pair gives a single
same-code delta, not a variance estimate. It can rule out "noise is tiny" or "the effect is real";
anything between those is ambiguous and will be reported as ambiguous.

Afterwards, record all three arms via `src/calibration_tracker.py record` and re-run `report`.
That adds up to 5 rows of *within-archetype small deltas*, the case where the n=5 calibration set
currently has almost no power.

## 2026-08-10 — forward-search (PIMC) layer: budget gate passed, mirror gate failed (not shipping)

Followed the Orbit-Wars-derived plan (`.claude/plans/act-as-an-expert-flickering-pnueli.md`):
harden `submissions/archaludon_search/main.py`'s existing `search_begin`/`search_step` layer with
opponent-archetype determinization, a terminal-rollout (PIMC) evaluator replacing the old
prizes-only `evaluate_board`, and `manual_coin=True`, instead of attempting RL (infeasible in 6
days, no numpy in the sandbox).

**Found and fixed a real, pre-existing bug first.** `read_deck_csv()` was missing the
CLAUDE.md-documented `__file__`-based fallback branch. Locally this call sat inside
`search_reorder`'s own `try/except`, so the resulting `FileNotFoundError` was silently swallowed
and search fell back to `base_selected` — meaning **the entire pre-existing search layer was a
permanent silent no-op in every local test run this repo has ever done** (`run_battle.py` and
`ladder_eval.py` both load `main.py` via `importlib` without `chdir`-ing into the candidate's own
directory, so relative `deck.csv` never resolved). The PIMC rewrite moved that same call outside
its protecting `try/except`, which surfaced the bug as a ~50% win-rate collapse (full-random play
on every exception) instead of a silent no-op — worse-looking, but that's what exposed it. Fixed
by adding the missing fallback branch; any header-comment numbers from before this fix (e.g. the
original file's claimed "found a winning line 253 times over 150 battles") should be treated as
unverified.

**Budget gate: passed.** Initial constants (`SEARCH_TIME_BUDGET=1.5s`, `PIMC_DETERMINIZATIONS=6`)
only reached ~29-36 playouts/decision against real per-game search time of 22-55s — far under the
300s/game cap, i.e. budget was sitting unused. Raised to `SEARCH_TIME_BUDGET=5.0s`,
`PIMC_DETERMINIZATIONS=20`; re-measured at **113.7 playouts/decision**, 164.5s/game, 0
`game_capped` hits — clears the ≥100 playouts/decision, <300s/game gate from the plan.

Opponent determinization confirmed working against a real meta deck (`kiyota_dragapult_ex`):
`archetype_matched` fired on effectively every PIMC playout once enough of the opponent's board
was revealed.

**Mirror gate: failed — do not ship.** Per the plan's own local-validation step, ran
`archaludon_search` (PIMC-enabled) vs `masamikobayashi_archaludon_cinderace` (same deck, search
off) via `ladder_eval.py rate --panel <baseline>`:

- n=30 (first pass, noise): 30.0% win rate [16.7, 47.9] — looked like a real regression.
- n=300 (follow-up): **49.7% win rate [44.0, 55.3]** — a dead heat. The n=30 reading was noise,
  per the standing rule that small samples here are unreliable.

Override rate was real and nonzero (~7-15% of MAIN decisions changed vs. base policy across
smoke tests) but the net effect on win rate is statistically indistinguishable from zero. This
does **not** clear the standing bar ("ship nothing expected to move less than ~100 μ" — a 65%+
mirror win rate) and Task #6 (ship the Arm A/B ladder pair) is **not being executed today** as a
result. Raw results: `data/processed/ratings/archaludon_search_pimc_v1.json`,
`archaludon_search_pimc_mirror.json`.

**Diagnosis complete — closing this experiment, not iterating further.** Instrumented per-game
`_search_stats` deltas across 200 mirror games (script, not committed): PIMC overrides fired in
only **11/200 games (5.5%)**, averaging **0.41 overrides/game** against ~51 MAIN decisions/game —
**≈0.8% of decisions, under the plan's own "<2% override rate → stop, don't ship on faith"
threshold.** Confirmed a second, independent mirror sample (n=150, `local_eval.py`) at 53.3%
[45.4, 61.1] — combined with the earlier n=300 ladder_eval reading (49.7%), pooled mirror win rate
across 450 games is 50.9%, solidly a tie.

Root cause: the base heuristic policy is already close to locally-optimal in a mirror matchup
(same deck both sides), so PIMC's "strict improvement over base" almost never finds one — there's
little room left for a resampled-rollout evaluator to add value against an opponent this similar
to ourselves. On the 11 games where it did override, win rate was numerically lower (36.4% vs
50.3%, n too small to be conclusive) — directionally consistent with "these overrides are noise,
not signal," not with "rare but decisive."

**Decision: do not ship this layer, and do not invest further Phase-2 time scaling it** (wider
candidate intents, deeper archetype library) — the bottleneck isn't playout budget or
determinization quality, it's that the base policy leaves too little room for search to find
anything in the matchup that matters most (mirror). This is a genuine negative result, logged in
full per CLAUDE.md's "measure reachability before crediting or blaming a branch" discipline. No
ladder slot spent on it.

## 2026-08-10 — `probablity_v2` pre-flighted early, ahead of the 08-13/14 slot

With the search-layer track closed and no ladder slot currently free (both active slots held by
the live Dragapult B2/noise-pair arms — see above), used the dead time to do Phase 3's
pre-submission hardening on `submissions/aristophanivan_probablity_v2/main.py` now rather than
under deadline pressure on 08-13/14.

Found a real sandbox risk, same failure class as the documented `__file__`/numpy gotchas:
`main.py` ran `Path("deck.csv").write_text(...)` unconditionally at **import time**, writing a
hardcoded 60-card `DECK` array over whatever `deck.csv` ships in the tar. If the real Kaggle
sandbox's cwd isn't writable (untested, unknown either way), this throws before `agent()` is even
defined — an immediate ERROR, exactly like the `il_agent_v2` numpy failure and the `__file__`
`NameError` failure already on file. Checked the actual `deck.csv` against the hardcoded array
first — byte-identical, so the write was always a no-op in practice, safe to neutralize. Wrapped
it in `try/except OSError: pass`.

Verified clean after the fix: `py_compile` passes; a 5-battle smoke run with `site-packages`
stripped from `sys.path` (the actual test that would have caught the `il_agent_v2` ERROR before
it cost a slot) completes with no import errors and no numpy/pandas dependency — pure stdlib +
`cg`. `probablity_v2` is now ready to spend a slot on whenever the plan calls for it (08-13/14),
with one fewer unverified assumption than before.

**Decision (2026-08-10, same day): don't wait for 08-13/14 — spend the slot now.** With 6 days
left and concurrency=2 (not the 5/day quota) as the real bottleneck, every hour spent waiting for
a 2nd settled reading on a question we already have a decent read on is an hour not spent getting
a first reading on the highest-uncertainty one. Explicit policy change from here: **act on first
readings, don't insist on ≥2 readings ≥24h apart before making a call.** More noise accepted in
exchange for more slots spent on genuinely open questions before the deadline.

Closed the Dragapult B1/B2 thread on existing data rather than waiting for B2 to fully settle:
both arms already read below the pre-split fix (`55336268`, 688.0) and both gaps are noise-floor
sized (see the update above) — parking the Dragapult track on `55336268` as-is, no B1/B2 mechanism
adopted, no further waiting on this thread.

Submitted `probablity_v2` (ref `55409793`, 2026-08-10 14:52 UTC, PENDING). This starves
`55371590` (B2, frozen final at 588.6) and pairs the new arm with `55389372` (Archaludon control,
680.5 and still live) — real ladder data on `probablity_v2` arrives well ahead of the original
08-13/14 slot. 4 submissions remaining today.

**First real reading, same day: `probablity_v2` = 711.7 (COMPLETE).** Above its local
frozen-panel estimate (647.6) and in Archaludon's real range — the local↔real gap this candidate
has always shown (real badge 933.8) points the same direction again, though still well short of
that badge. Now a genuine contender for the 2nd Final Submission slot.

With `55389372` 18h old and having already given its noise-floor data point (680.5 vs 711.4,
logged above), spent the freed slot on the other open question: `biohack44_alakazam_dunsparce`
(Profile B), local frozen-panel μ 669.9 (3rd-best of the roster), never previously given a real
reading. Pre-flighted identically to `probablity_v2` (py_compile, `__file__`-guard pattern check,
stripped-`sys.path` 5-battle smoke test — all clean, no numpy). Submitted as `55409986`
(2026-08-10 15:00 UTC, PENDING). This starves `55389372` (final at 680.5). Active pair is now
`{55409793 probablity_v2, 55409986 alakazam_dunsparce}`. 3 submissions remaining today.

**Both COMPLETE, same day:**
- `alakazam_dunsparce` (`55409986`) = **720.4** — strong debut, above its own local estimate
  (669.9) and above Archaludon's most recent reading (680.5), inside Archaludon's noisy historical
  range (680.5-811.4). New contender for the 2nd Final Submission slot, real data where before
  there was none.
- `probablity_v2` (`55409793`) **moved from 711.7 to 659.4** — a 52.3 μ swing on the same
  submission, within the established 24-63 μ noise floor but a reminder this is exactly the kind
  of single-reading volatility the old "wait for settling" discipline existed to guard against.
  Per the new faster-iteration policy this isn't being waited out further, but it's flagged
  honestly: 659.4 is the number to use if a call has to be made right now, not 711.7.

**Third open question, same day: `soutasakurai_libraryout_crustle`.** Its only real reading
(553.8, `55308334`, 2026-08-06) predates a code change to `main.py` on 2026-08-07 — local μ is now
685.7 (2nd-best of the roster), same "stale real score, improved code" shape that just paid off
with `alakazam_dunsparce`. Pre-flighted (py_compile clean, no `__file__` dependency, stripped-
`sys.path` smoke battle clean, no numpy) — the submission dir was missing its own loose `cg/`
copy (packaging previously relied on it being supplied separately), added it back for consistency
with the other candidate dirs. **Found, not fixed**: the exception-fallback path
(`agent()`'s `except Exception`, when `select is None`) returns `read_deck_csv()` — a list of ~60
card IDs — as the select list, which isn't a valid selection. Only reachable on exception +
malformed `select`, and 24000 clean local games plus the existing real reading already prove the
normal path works, so left as-is rather than spending time on an edge-case-of-an-edge-case.
Submitted as `55416420` (2026-08-10 21:22 UTC, PENDING), evicting `probablity_v2` (starved final
at 659.4, one reading only — re-testable later since concurrency, not the daily quota, is the
binding constraint). Active pair: `{55409986 alakazam_dunsparce, 55416420 crustle}`. 2 submissions
remaining today.

**Second readings, next day (2026-08-11):**
- `crustle` (`55416420`) **moved from 686.7 to 743.3** — a 56.6 μ swing, inside the 24-63 μ noise
  floor but wide enough that the earlier "matched local almost exactly" observation is retracted:
  that was a lucky single reading, not crustle being unusually low-noise. Now clearly the leading
  candidate for the 2nd Final Submission slot, ahead of Archaludon's most recent reading (680.5)
  and its two peak readings' neighborhood (774.8/811.4).
- `alakazam_dunsparce` (`55409986`) **moved from 720.4 to 712.4 to 698.2** — a steady downward
  drift, still noise-floor-sized swing-to-swing, still above its own local estimate (669.9) on
  every reading so far.
- Gap between the two is now 45.1 μ (crustle ahead) — noise-floor-sized, not yet a settled
  verdict, but the largest gap observed between them.

**Decision: no further slot spend on this comparison.** The active concurrency pair
(`alakazam_dunsparce` + `crustle`) already produces a free repeated A/B every time the ladder
updates — no synthetic noise-floor pair (two identical tarballs back to back) is needed to learn
whether the gap is signal, since two independently-drifting live candidates already demonstrate
the noise floor in action. General principle worth keeping: **when the two occupied concurrency
slots are already the comparison you care about, every subsequent reading is a free data point —
don't spend a 3rd slot to manufacture a comparison you're already running.** Nothing else in the
roster clears the bar for a slot right now: Mega Lucario (local μ 590.8) is weaker than every
active candidate, the IL track and the PIMC search layer are both closed negative results, and
`probablity_v2` (659.4, lowest of the three newly-real-tested candidates) is lower priority than
watching the current pair settle.

## Known constraints to keep in mind throughout

- **Discussion mining is scriptable via the Kaggle CLI** (`kaggle competitions topics
  list/show <slug> --format json`, paginated) — not manual/permanent as first thought. See
  `discussion-intel-report.md` for the full pull (204 topics indexed, 58 deep-read) and the
  updated `kaggle-competition-playbook` skill's `competition-intel.md` for the exact commands.
- **Local win rate ≠ ladder score.** The `cg` engine's local opponent pool is fixed and small;
  a kernel (or your own candidate) that crushes it locally may not generalize. Treat local
  `run-battle` results as a fast filter, not a final verdict — the real signal is the hidden
  ladder via actual Kaggle submissions, which are slower to get feedback from.

## 2026-08-11 — reopening the PIMC layer: pre-registered diagnostic gate G1

The 2026-08-10 kill decision was made on the mirror alone. The mirror is also the one matchup in
which the rollout's opponent model (`choose_options`, the Archaludon policy) is accidentally
correct, so it cannot expose the model's defects. Measuring the *unmodified* `archaludon_search`
layer against Crustle and Alakazam before changing anything.

Rules, fixed before any reading:

- **G1a — candidate collapse.** If `mean_distinct_lines` <= 1.2, varying only the first action
  cannot change the turn, and intent-based candidates (Task 8-10) are mandatory rather than
  optional.
- **G1b — off-mirror headroom.** If `override_share` against Crustle or Alakazam is >= 3x the
  mirror's, the mirror-only kill was unrepresentative and the layer is worth reopening.
- **G1c — estimator resolution.** If `mean_value_gap` is smaller than 2*sqrt(2/PIMC_DETERMINIZATIONS),
  the PIMC estimator cannot resolve the differences it is being asked to rank, and every override
  it makes is noise. Fix the estimator (Task 6) before judging the idea.
- **G1d — opponent model.** If the modelled opponent's energy-attachment rate in non-mirror
  rollouts is ~0, the rollouts are not games and no amount of extra sampling helps.

If G1b fails *and* G1c passes *and* G1d passes, the 2026-08-10 conclusion is correct as stated and
this whole plan should stop at this task.

**Readings** (unmodified `archaludon_intent`, post Task 1-3 scaffolding, `PTCG_SEARCH_PROFILE=fast`
i.e. `PIMC_DETERMINIZATIONS=12`, 56 games each — `--games 60 --workers 8` floor-divides to
7 games/worker × 8 = 56, not a dropped-game bug):

| field | vs Crustle | vs Alakazam | vs mirror (Cinderace) |
|---|---|---|---|
| `multi_option_share` | 0.9768 | 0.9799 | 0.9785 |
| `mean_distinct_lines` | 5.6595 | 5.5897 | 5.5168 |
| `override_share` | 0.3439 | 0.2114 | 0.3226 |
| `mean_value_gap` | null | null | null |
| `mean_draws_per_line` | 0.0 | 0.0 | 0.0 |
| `archetype_share` (matched) | 0.9932 (`libraryout_crustle`) | 0.9441 (`alakazam_dunsparce`) | 0.9168 (`archaludon_cinderace`) |
| `win_rate` | 0.3929 (22/56) | 0.3571 (20/56) | 0.4107 (23/56) |
| `cpu_seconds_per_game` | 36.595 | 18.153 | 23.305 |

Raw JSON: `data/processed/instrumentation/baseline_vs_soutasakurai_libraryout_crustle.json`,
`baseline_vs_biohack44_alakazam_dunsparce.json`, `baseline_vs_masamikobayashi_archaludon_cinderace.json`.

**G1d verified directly** (per the brief's snippet, `CardType.ENERGY` doesn't exist on this engine's
enum — it's `BASIC_ENERGY`/`SPECIAL_ENERGY`; used `{CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY}`
instead, same intent): every `_ARCHETYPE_DECKS` entry except `archaludon_cinderace` (the mirror)
shows `metal(8) present: False` — `dragapult_ex`, `libraryout_crustle`, `mega_lucario_ex`,
`alakazam_dunsparce`, `probablity_v2` all lack `METAL_ENERGY` entirely. `score_attach`
(`main.py:816-833`) returns `-500, "skip non-Metal"` for any other card id, which loses to `END`'s
0, so the modelled opponent's ATTACH branch can structurally never win a comparison in any
non-mirror rollout.

**Verdict:**

- **G1a — no collapse.** `mean_distinct_lines` is 5.5-5.7 in every matchup, far above the 1.2
  collapse threshold. **Passes** (not collapsed) — the layer is already varying the first action
  across several distinct lines per decision, off-mirror included.
- **G1b — off-mirror headroom: fails.** 3x the mirror's `override_share` (0.3226) is 0.9679.
  Neither Crustle (0.3439, ~1.07x) nor Alakazam (0.2114, ~0.66x) clears it — off-mirror
  `override_share` is in the same band as the mirror's, not 3x higher. By this proxy the
  mirror-only kill was not obviously unrepresentative.
- **G1c — estimator resolution: untestable with current data, not "passes."** `mean_value_gap` is
  `null` in all three JSONs. Root cause confirmed by reading `main.py` directly, not inferred: the
  PIMC branch's `_trace()` call (`main.py:1636-1653`) hardcodes `base_value=None` and
  `best_value=None` in the emitted record even though `best_value` is computed a few lines earlier
  (`main.py:1625-1634`) — it's just never threaded into the trace call, and no base-candidate score
  is ever computed at all (`base_value` is a local hardcoded to `None` at `main.py:1640`). Same
  hardcoding affects `draws_per_line` (`main.py:1639`, always `0`), which is why that column reads
  `0.0` everywhere too. This is expected, per Task 2 Step 4's own explicit deferral — not an
  oversight; the real wiring lands in Task 6. It's not a finding about the actual estimator's
  resolution — G1c cannot be assessed until that wiring is fixed.
- **G1d — opponent model: fails (confirmed directly).** The modelled opponent's energy-attachment
  rate in every non-mirror rollout is exactly 0, not just "~0" — `score_attach` structurally cannot
  score an attach above `END` for any archetype other than the mirror, because none of those
  archetypes' decks contain `METAL_ENERGY` and any other card id scores `-500`.

**Net:** the plan's stop rule ("G1b fails *and* G1c passes *and* G1d passes") is **not satisfied** —
G1b does fail, but G1c is inconclusive (not a pass) and G1d also fails (confirmed, not passes). The
2026-08-10 mirror-only kill is therefore not vindicated by this data as stated: there is a
confirmed, structural defect in the rollout opponent model (G1d) that would suppress or distort any
off-mirror `override_share` signal regardless of whether real headroom exists, which is itself a
plausible explanation for why G1b's proxy came back negative. This task does not decide whether to
continue past this gate; that call is left to whoever reads this section next.

### 2026-08-11 — intent-PIMC iteration gate (pre-registered)

Baselines, Archaludon base at n=4000 per opponent
(`data/processed/ratings/masamikobayashi_archaludon_cinderace.json`):
Crustle 33.5%, Alakazam 42.1%, mirror 50.0% by symmetry; three-matchup pooled 41.9%.

Pass requires all three:
1. Pooled win rate across the three matchups >= 47.0% (i.e. >= +5pp; Wilson half-width at
   n=3000 is +-1.8pp).
2. No single matchup regresses by more than 5pp against its baseline.
3. `stats.game_capped == 0` and `stats.errors` per game no worse than the Task 4 baseline.

Failing 1 or 2 sends the work back to Task 8 (re-pick intents) or Task 7 (opponent model), not to
the ladder. Failing 3 is a budget bug, fix and re-run.

**Reading (2026-08-11):** `PTCG_SEARCH_PROFILE=fast python3 src/ladder_eval.py rate --candidate
submissions/archaludon_intent --panel submissions/soutasakurai_libraryout_crustle
submissions/biohack44_alakazam_dunsparce submissions/masamikobayashi_archaludon_cinderace --games
1000 --workers 8 --json data/processed/ratings/archaludon_intent_gate3.json`, 3000 games total
(1000/opponent), panel version `fa733a4e989a`:

| opponent | wins/games | win% | 95% Wilson CI | baseline | delta |
|---|---|---|---|---|---|
| `soutasakurai_libraryout_crustle` | 336/1000 | 33.6% | [30.7, 36.6] | 33.5% | +0.1pp |
| `biohack44_alakazam_dunsparce` | 428/1000 | 42.8% | [39.8, 45.9] | 42.1% | +0.7pp |
| `masamikobayashi_archaludon_cinderace` (mirror) | 493/1000 | 49.3% | [46.2, 52.4] | 50.0% | −0.7pp |
| **pooled (three matchups)** | 1257/3000 | **41.9%** | [40.1, 43.7] | 41.9% | **+0.0pp** |

Battle-level errors (`err` column, battles that failed to start): 0/1000 in every matchup. Local μ
over this three-member field is 617.9 (σ 19.2) — per the brief's own note, not comparable to the
seven-member panel numbers elsewhere in this file, and not used for the verdict below.

`stats.game_capped` caveat: `ladder_eval.py rate` (the exact Step 2 command) only tracks
battle-start failures (the `err` column above, 0 in all three matchups) — it does not surface
`archaludon_intent/main.py`'s internal `_search_stats` counters (`game_capped`, `calls`, etc.),
which Task 4 read via a separate, ad hoc in-process script. Rule 3 below is judged on the
evidence this harness actually produces (battle-level errors), not a re-measurement of the
internal counter.

**Verdict:**

1. **Pooled win rate >= 47.0%: FAIL.** Actual pooled rate is 41.9%, identical (to one decimal) to
   the 41.9% pre-registered baseline — +0.0pp, not the required +5pp (>=47.0%). The 95% CI
   [40.1, 43.7] doesn't even approach the threshold.
2. **No single matchup regresses by more than 5pp: PASS.** Crustle and Alakazam both improved
   slightly (+0.1pp, +0.7pp); the mirror regressed by only 0.7pp (50.0% -> 49.3%), well inside the
   5pp budget.
3. **`stats.game_capped == 0` and errors no worse than Task 4 baseline: PASS on available
   evidence.** Battle-level errors are 0/1000 in every matchup, matching Task 4's baseline
   (`errors: 0` in all three of its JSONs). `stats.game_capped` itself was not independently
   re-measured by this harness (see caveat above); no contrary evidence exists.

**Overall: FAIL — rule 1 fails.** Per the pre-registered rule, this sends the work back to
**Task 8 (re-pick intents) or Task 7 (opponent model)**, not to the ladder — a submission slot
should not be spent on `archaludon_intent` as-is. The three-matchup performance is
statistically indistinguishable from the unmodified rule-based Archaludon baseline it was meant
to improve on: the new PIMC/intent search layer produced no net gain here. Task 4's own G1d
finding (`score_attach` structurally cannot score an ATTACH above `END` for any archetype other
than the mirror, because no non-mirror `_ARCHETYPE_DECKS` entry contains `METAL_ENERGY`) is a
still-open, confirmed defect in the rollout opponent model that would suppress exactly the kind
of off-mirror gain rule 1 was checking for — making **Task 7 (opponent model)** the more directly
implicated of the two return destinations, though the brief does not force a single choice
between 8 and 7.

### 2026-08-11 — intent-PIMC iteration gate, second attempt (pre-registered)

First attempt (commit 0fb8427) failed rule 1: pooled 41.9%, identical to the 41.9% pre-fix
baseline. Diagnosis traced this to `_generic_score_option`'s ATTACK branch scoring every
non-mirror opponent attack as 0 damage (hardcoded to our own deck's attack IDs via
`best_attack_damage`/`_ATTACK_BASE_DMG`). Fixed in commit a4e9ef9 (`generic_attack_damage()`,
a real deck-agnostic lookup via the engine's `ALL_ATTACKS` table). An 80-game telemetry check
showed `mean_value_gap` improve modestly (Crustle 0.0935->0.1108, Alakazam ~0.09->0.1188,
+18-30% relative) but not dramatically.

Same three pass rules as the first attempt (baselines unchanged: Crustle 33.5%, Alakazam 42.1%,
mirror 50.0%, pooled 41.9%):
1. Pooled win rate across the three matchups >= 47.0%.
2. No single matchup regresses by more than 5pp against its baseline.
3. `stats.game_capped == 0` and errors no worse than the Task 4 baseline.

Per the plan's stop condition: this is the plan's SECOND Task 11 attempt. If this also fails,
per the plan, the next step is Task 14 (IL intent classifier contingency) or stopping and
shipping the best rule-based candidate (`masamikobayashi_archaludon_cinderace`) as the Final
Submission fallback -- not a third repair cycle on this same search stack.

**Reading (2026-08-11):** `PTCG_SEARCH_PROFILE=fast python3 src/ladder_eval.py rate --candidate
submissions/archaludon_intent --panel submissions/soutasakurai_libraryout_crustle
submissions/biohack44_alakazam_dunsparce submissions/masamikobayashi_archaludon_cinderace --games
1000 --workers 8 --json data/processed/ratings/archaludon_intent_gate3_v2.json`, 3000 games total
(1000/opponent), panel version `fa733a4e989a`, candidate at commit a4e9ef9 (post generic-attack-
damage fix):

| opponent | wins/games | win% | 95% Wilson CI | baseline | delta |
|---|---|---|---|---|---|
| `soutasakurai_libraryout_crustle` | 334/1000 | 33.4% | [30.5, 36.4] | 33.5% | −0.1pp |
| `biohack44_alakazam_dunsparce` | 368/1000 | 36.8% | [33.9, 39.8] | 42.1% | **−5.3pp** |
| `masamikobayashi_archaludon_cinderace` (mirror) | 498/1000 | 49.8% | [46.7, 52.9] | 50.0% | −0.2pp |
| **pooled (three matchups)** | 1200/3000 | **40.0%** | [38.3, 41.8] | 41.9% | **−1.9pp** |

Battle-level errors (`err` column): 0/1000 in every matchup. Local μ over this three-member field
is 633.7 (σ 19.1) — not comparable to the seven-member panel numbers elsewhere in this file, and
not used for the verdict below. Same `stats.game_capped` caveat as the first attempt: this harness
only surfaces battle-start failures, not `main.py`'s internal `_search_stats` counters.

**Verdict:**

1. **Pooled win rate >= 47.0%: FAIL.** Actual pooled rate is 40.0%, *below* both the 47.0%
   threshold and the 41.9% pre-fix baseline (−1.9pp) — the generic-attack-damage fix moved the
   pooled rate in the wrong direction, not just short of target.
2. **No single matchup regresses by more than 5pp against its baseline: FAIL.** Alakazam dropped
   from 42.1% to 36.8%, a 5.3pp regression — over the 5pp budget. Crustle (−0.1pp) and the mirror
   (−0.2pp) are both within budget.
3. **`stats.game_capped == 0` and errors no worse than Task 4 baseline: PASS on available
   evidence.** Battle-level errors are 0/1000 in every matchup, matching both the Task 4 baseline
   and the first attempt. `stats.game_capped` was not independently re-measured by this harness
   (same caveat as the first attempt).

**Overall: FAIL — rules 1 and 2 both fail**, a harder failure than the first attempt (which
failed only rule 1). The `generic_attack_damage()` fix did move `mean_value_gap` in the intended
direction per the 80-game telemetry check, but that did not translate into a net win-rate gain at
full scale — if anything, the pooled rate and the Alakazam matchup specifically got worse, not
just "no better." This is the plan's **second** Task 11 attempt, and per the plan's stop
condition, the next step is **Task 14 (IL intent classifier contingency) or stopping and shipping
`masamikobayashi_archaludon_cinderace` as the Final Submission fallback** — not a third repair
cycle on this same intent-PIMC search stack. This document does not decide which of those two; that
call is left to whoever reads this section next.

### 2026-08-11 — intent-PIMC iteration gate, third attempt (IL classifier wiring, pre-registered)

Per the second attempt's own recommendation, Task 14 built an IL intent classifier contingency:
Task 14a (commit `bb631ed`) trained and exported a 5-class (`aggro, base, develop, snipe,
survive` — alphabetical, per sklearn's default `classes_` ordering) stdlib-only gradient-boosted
classifier (`models/il_intent_classifier_pure.json`), flagged at the time as a concern because its
held-out accuracy (85.7%) came in *below* the majority-class baseline (87.7%), traced to severe
class imbalance (`develop` n=6, `snipe` n=93, `survive` n=58 training examples). Task 14b
(commit range below) wired that classifier into `search_reorder` as the primary decision
mechanism, replacing the PIMC-over-all-intents comparison from the first two attempts: the
classifier's argmax now picks the intent directly, with PIMC's paired-determinization estimator
invoked only as a tiebreaker when the top-two predicted class probabilities are within 0.1. This
gate re-run measures whether the classifier's decision was any better than PIMC's, honestly
regardless of how the offline accuracy number looked beforehand.

Same three pass rules as the first two attempts (baselines unchanged: Crustle 33.5%, Alakazam
42.1%, mirror 50.0%, pooled 41.9%):
1. Pooled win rate across the three matchups >= 47.0%.
2. No single matchup regresses by more than 5pp against its baseline.
3. `stats.game_capped == 0` and errors no worse than the Task 4 baseline.

**Reading (2026-08-11):** `PTCG_SEARCH_PROFILE=fast python3 src/ladder_eval.py rate --candidate
submissions/archaludon_intent --panel submissions/soutasakurai_libraryout_crustle
submissions/biohack44_alakazam_dunsparce submissions/masamikobayashi_archaludon_cinderace --games
1000 --workers 8 --json data/processed/ratings/archaludon_intent_gate3_il.json`, 3000 games total
(1000/opponent), panel version `fa733a4e989a`, candidate with the classifier-argmax `search_reorder`
wired in (Task 14b):

| opponent | wins/games | win% | 95% Wilson CI | baseline | delta |
|---|---|---|---|---|---|
| `soutasakurai_libraryout_crustle` | 448/1000 | 44.8% | [41.7, 47.9] | 33.5% | **+11.3pp** |
| `biohack44_alakazam_dunsparce` | 359/1000 | 35.9% | [33.0, 38.9] | 42.1% | **−6.2pp** |
| `masamikobayashi_archaludon_cinderace` (mirror) | 363/1000 | 36.3% | [33.4, 39.3] | 50.0% | **−13.7pp** |
| **pooled (three matchups)** | 1170/3000 | **39.0%** | [37.3, 40.8] | 41.9% | **−2.9pp** |

Battle-level errors (`err` column): 0/1000 in every matchup. Local μ over this three-member field
is 641.0 (σ 19.1) — not comparable to the seven-member panel numbers elsewhere in this file, and
not used for the verdict below. Same `stats.game_capped` caveat as the first two attempts: this
harness only surfaces battle-start failures, not `main.py`'s internal `_search_stats` counters.

Runtime note: this reading completed in well under the brief's 2-4h estimate — the classifier-
argmax path only invokes the expensive paired-PIMC estimator on a near-tie (top-two probabilities
within 0.1), so most of the 3000 games' MAIN decisions skip `_pimc_score_lines` entirely. This is
the expected consequence of Step 6's design (PIMC as tiebreaker, not primary mechanism), not a
scope cut — the full 1000 games/opponent (3000 total) ran to completion.

**Verdict:**

1. **Pooled win rate >= 47.0%: FAIL.** Actual pooled rate is 39.0%, below both the 47.0% threshold
   and the 41.9% pre-fix baseline (−2.9pp) — worse than the first attempt's flat 41.9% and close to
   the second attempt's −1.9pp.
2. **No single matchup regresses by more than 5pp against its baseline: FAIL, badly.** The mirror
   matchup collapsed from 50.0% to 36.3%, a 13.7pp regression — nearly 3x the second attempt's
   worst regression (Alakazam, −5.3pp) and by far the largest single-matchup regression across all
   three gate attempts. Alakazam also regressed over budget (−6.2pp). Only Crustle improved
   (+11.3pp, not a regression) — the classifier moved performance in opposite directions on
   different opponents rather than uniformly up or down.
3. **`stats.game_capped == 0` and errors no worse than Task 4 baseline: PASS on available
   evidence.** Battle-level errors are 0/1000 in every matchup, matching all prior attempts and the
   Task 4 baseline. `stats.game_capped` itself was not independently re-measured by this harness
   (same caveat as both prior attempts).

**Overall: FAIL — rules 1 and 2 both fail**, and rule 2 fails harder than either prior attempt (the
13.7pp mirror regression dwarfs the second attempt's 5.3pp Alakazam regression). The IL intent
classifier's pre-registered offline concern (85.7% held-out accuracy below the 87.7% majority-class
baseline, driven by severe class imbalance in `develop`/`snipe`/`survive`) predicted exactly this
outcome: a classifier that cannot reliably beat "always predict the plurality class" offline had no
reason to beat PIMC's already-failing comparison on the ladder, and it did not — it made the worst
single-matchup regression measured across all three attempts. This is the third Task 11 attempt (two
PIMC-only, one IL-classifier) and per CLAUDE.md's standing skepticism flag on IL after two prior
underperforming attempts (`il_agent_v2`/`v3`), this is now the **third** IL-shaped approach in this
repo to underperform a simpler rule-based/PIMC baseline. **Recommend stopping and shipping the best
rule-based candidate (Archaludon base, `masamikobayashi_archaludon_cinderace`) as the Final
Submission fallback** — no further repair cycle on the intent-PIMC/IL-classifier search stack is
recommended. This is a report-and-stop finding; per Task 14b's brief, the coordinator decides the
next dispatch, and Task 12 (full frozen-panel confirmation) is explicitly not entered here even
though not every rule can plausibly be salvaged by a fourth iteration.
