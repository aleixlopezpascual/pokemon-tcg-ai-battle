# Baseline comparison — what to start from

Compares every real, verifiable data point gathered on 2026-08-06: the live official
leaderboard, 12 pulled public kernels (see `notebook-audit-template.md`), and a third-party
competitor workspace (`pulled/TomBombadyl__kaggle_pokemon/`, public GitHub, no LICENSE file —
read for ideas/facts, do not copy code verbatim without permission).

## Live leaderboard reality check (2026-08-06)

Top of `kaggle competitions leaderboard pokemon-tcg-ai-battle --show`: **~1188.4** (team LiamK),
next several teams **1100-1150**. This is the bar any candidate baseline needs to approach.

## Ranked candidates

| Rank by evidence | Source | μ / LB | Approach | Verdict |
|---|---|---:|---|---|
| 1 | TomBombadyl `archaludon_rules` + R7 empty-bench guard, `archaludon_ex_cinderace.csv` (ref `54083197`, 2026-06-28) | **1196.1** (peak 1224.2) | Rule-based, hand-tuned MAIN priorities + mandatory-bench guard, **no RL/training** | **Strongest verified data point found**, at/above today's live #1. But is a 5-week-old reading — μ drifts with matchmaking and meta has had 5 more weeks to shift (their own README flags a historic "Crustle anti-ex spike" already happened once). Treat as "proof this class of approach works," not "guaranteed still #1." |
| 2 | `romanrozen/strong-start-baseline-agent-v10-lb-950` (Kaggle kernel, 183 votes, run 2026-08-03) | **LB 950+** (self-reported) | Unknown internals — pull and audit | Recent (3 days before our check) and community-validated by vote count. Worth auditing early. |
| 3 | TomBombadyl `dragapult_crispin` (official kiyotah Dragapult sample + R7 bench guard), ref `53989933` | **880.9** | Official sample, verbatim + a bench-guard wrapper, **no training** | Confirms: the *official Kiyota sample itself*, with one small correctness fix (never leave bench empty), is already a strong, simple floor. |
| 4 | `makthanithin/pokemon-tcg-ai-battle-1084-5-baseline` (Kaggle kernel, unaudited) | **1084.5** (self-reported title) | Unknown | Also worth an early pull — close to live leaderboard top, self-reported, recent-ish. |
| 5 | TomBombadyl `SearchScorer` + shallow search, real-mined Mega Lucario ex deck | **660.5** | Rules + shallow search, **no training** | Their own "best home-grown brain" — still rules/search, not ML. |
| — | TomBombadyl MCTS/RL brains (`lucario_mcts_basic` 651.3, `lucario_mcts_field` v5 580.6, a from-scratch MCTS/transformer Alakazam ~185) | 185-651 | Trained (MCTS, PPO, transformer) | **Every trained approach they shipped lost to plain rules/search on the ladder.** Their own standing ruling (R3): "an ML method must beat [rules] on the ladder to ship" — none has yet, in their experience. |

## The takeaway

**Every top real data point found — ours and theirs — is rule-based, not trained.** The single
highest-value engineering investment demonstrated across all sources isn't a smarter model, it's
a **correctness guard**: never leave the bench empty / never have no legal active Pokémon
(`no_active` losses are a real, recurring μ sink in TomBombadyl's own loss traces, and directly
mirrored by this repo's own `run-battle` skill note that illegal-deck/illegal-state submissions
get rejected or lose outright).

## Update (2026-08-07) — working baseline chosen and submitted

Two submissions happened before this update, and both taught real lessons:

1. **First submission**: the raw official Kiyota Mega Lucario ex sample (`submissions/kiyota_mega_lucario_ex/`). ERRORed once (a path-handling bug I introduced — see `10-day-plan.md` submission log — Kaggle runs `main.py` via `exec()` with **no `__file__` in scope**, so any `__file__`-based path logic must be guarded with `try/except NameError`). Fixed, resubmitted, **COMPLETE at 439.9-450.9 μ** — a real but low score, expected for an untuned "Intermediate Level" teaching sample with no matchup logic or correctness guards.
2. **Second submission**: found `masamikobayashi/a-sample-archaludon-75-wr-vs-my-1300-starmie` — a fully self-contained (main.py + deck.csv both in the notebook, no external dataset needed), matchup-tuned Archaludon ex/Cinderace agent (Crustle/Alakazam/Hop/Lucario-specific logic, grid-searched thresholds). It **independently confirms rank #1 from this doc's original table** (TomBombadyl's `archaludon_rules` archetype, 1196-1224 μ) — two unrelated sources converging on the same archetype as strongest. Locally it beats our own submitted Lucario baseline 70% of the time (20 games) and already correctly guards the `__file__`/`exec()` quirk. **Submitted as our new working baseline** (`submissions/masamikobayashi_archaludon_cinderace/`, ref `55308121`).

This is now the baseline to iterate on going forward, not the Lucario sample. See `notebook-audit-template.md` for the full per-kernel writeups (including `masamikobayashi/prize-card-tracking-1300-starmie`'s reusable `PrizeTracker` class for imperfect-information deck inference, and `makthanithin`'s tar-validation-before-submit pattern, now adopted here).

## Local eval harness — built, and honestly calibrated (2026-08-07)

Single-opponent `run-battle` testing was repeatedly misleading (Lucario 100% vs random →
490.8 real; Great Tusk 80% vs Archaludon locally → scored *lower* than Archaludon for real).
Built `src/local_eval.py` — pools a candidate's win rate across a roster of real opponents
(random baseline + our 3 submitted agents) with Wilson 95% confidence intervals, not just one
pairwise number.

**Calibration check against our 3 known real scores:**

| | Pooled local WR | Real ladder μ |
|---|---:|---:|
| Great Tusk | 73.3% | 553.8 |
| Archaludon | 65.0% | 643.1 |
| Lucario | 51.7% | 490.8 |

**Conclusion**: the harness correctly identifies Lucario as clearly weakest (both rankings
agree) — good as a coarse filter for "is this candidate obviously bad." But it ranks Great Tusk
above Archaludon locally while the real ladder ranks them the other way — **it cannot reliably
distinguish between two roughly-comparable-strength candidates**. Our roster of 3-4 same-tier
rule-based agents isn't diverse enough to substitute for the real ladder's much larger, more
varied field. Use this harness to catch obviously-broken or clearly-weak candidates before
spending a submission; do not use it to pick a winner between two candidates that both look
decent locally — only a real submission answers that with any confidence, given the resources
available here.

## Recommended next steps from here

1. **Wait for ≥2 stable μ readings on ref `55308121`** before deciding whether Archaludon-as-is is good enough or needs the next round of tuning — don't react to the first reading (own research + generic Kaggle pattern both say early scores are noisy/inflated).
2. Add the one correctness class of fix that shows up as high-value across every source we've found — including this new one — a **mandatory-bench / never-illegal-action guard**, so the agent never returns a selection that causes a `no_active` or deck-legality loss. Check whether `masamikobayashi`'s agent already has this (it has extensive matchup logic; worth confirming the empty-bench case specifically is covered) before assuming it needs bolting on.
3. Build 1-2 more local opponent agents from other pulled kernels (Dragapult ex, or a from-scratch build of TomBombadyl's documented Archaludon lever levels) so local testing isn't just "vs random" or "vs our one other submission" — per the `kaggle-competition-playbook` skill's tiered-opponent-system pattern. Local win rate still won't reliably predict ladder μ (confirmed twice now: our two submissions' real scores didn't match what local win rate alone would have predicted), but a broader opponent pool is a better filter than a single fixed one.
4. Run `myso1987/ptcg-ai-battle-leaderboard-deck-meta-by-score-band` (a live leaderboard-deck-archetype scraper, multi-hour for full mode) when there's room in the schedule — it would give a real, current "what's winning at the top score bands" answer instead of inferring from kernel titles.
5. Only reach for search/MCTS/RL *after* the rule-based baseline's ceiling is clear — per TomBombadyl's Ruling R3/R4, pilot-quality dominates deck choice, and no trained approach in any evidence gathered (theirs or the wider kernel pool) has beaten a well-guarded rule-based one yet.

## Facts worth carrying forward as-is (official game rules, not proprietary code)

From `pulled/TomBombadyl__kaggle_pokemon/RULINGS.md` Part 4 (their own citations of the
competition's official docs — verify independently against this repo's actual `cg/api.py` via
`game-engine-analyst` before relying on it, since they flag it as unverified-against-engine
themselves):

- **Scoring**: TrueSkill-style N(μ, σ²) per submission. μ moves on **win/loss/draw only per
  episode** — margin and speed don't affect it. New agents get heavy early episode volume so σ
  shrinks fast; a μ≈600 first reading is just the self-validation prior, not real signal.
- **Submission limits**: **5 uploads/team/day**, but only **2 Final Submissions count** for
  placement, and those must be **manually selected** — auto-select may pick your latest two
  uploads rather than your best two. Budget the 10-day plan's final days around this.
- **Imperfect information**: opponent's board (active/bench/discard/attached) is visible;
  opponent's hand contents, deck order, and prizes are hidden (only counts are visible). Build
  decision logic accordingly rather than assuming full state visibility.
- **Clock**: 10 minutes total per player per game; running out is an immediate loss.
