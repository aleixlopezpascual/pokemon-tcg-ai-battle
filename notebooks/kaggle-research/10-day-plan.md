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

## Known constraints to keep in mind throughout

- **Discussion mining is scriptable via the Kaggle CLI** (`kaggle competitions topics
  list/show <slug> --format json`, paginated) — not manual/permanent as first thought. See
  `discussion-intel-report.md` for the full pull (204 topics indexed, 58 deep-read) and the
  updated `kaggle-competition-playbook` skill's `competition-intel.md` for the exact commands.
- **Local win rate ≠ ladder score.** The `cg` engine's local opponent pool is fixed and small;
  a kernel (or your own candidate) that crushes it locally may not generalize. Treat local
  `run-battle` results as a fast filter, not a final verdict — the real signal is the hidden
  ladder via actual Kaggle submissions, which are slower to get feedback from.
