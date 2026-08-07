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

**4 of 5 daily uploads remain for 2026-08-06.** Only 2 Final Submissions count for placement and must be *manually* selected later — don't forget this near the deadline.

## Known constraints to keep in mind throughout

- **Discussion mining is manual, permanently.** No API or plain-fetch path exists for
  Kaggle's per-competition forum threads — don't burn time trying to script it.
- **Local win rate ≠ ladder score.** The `cg` engine's local opponent pool is fixed and small;
  a kernel (or your own candidate) that crushes it locally may not generalize. Treat local
  `run-battle` results as a fast filter, not a final verdict — the real signal is the hidden
  ladder via actual Kaggle submissions, which are slower to get feedback from.
