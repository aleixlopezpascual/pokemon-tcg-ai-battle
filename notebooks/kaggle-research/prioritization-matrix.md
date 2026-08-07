# Prioritization matrix — which kernels/threads to audit first

Pulled via `python src/fetch_kaggle_kernels.py --list-only`, ~50 public kernels exist for
`pokemon-tcg-ai-battle`. A full audit budget (see `10-day-plan.md`) covers maybe 8-12 of
these in depth. Score each candidate on the axes below before spending audit time on it.

## Scoring axes

| Axis | What it signals | How to read it |
|---|---|---|
| **Vote count** | Community validation | Proxy only — high votes can mean "popular starter template" rather than "actually strong." Weight it, don't trust it alone. |
| **Disclosed LB score** | Real competitive strength | Title/description sometimes states a leaderboard score directly (e.g. `strong-start-baseline-agent-v10-lb-950`, `multiply-agent-best-940-lb`, `pokemon-tcg-ai-battle-1084-5-baseline`). Compare against the live leaderboard range (~1080-1190 at the top as of 2026-08-06) to gauge how competitive it actually is *now*, not just relative to other kernels. |
| **Recency** | Meta relevance | `lastRunTime` matters — meta-snapshot notebooks are dated (18-July, 07-July, 06-29) and the meta shifts over a multi-month competition. A high-vote notebook from early in the competition may target an outdated meta. Prefer the most recent meta-snapshot/analysis over older ones when they conflict. |
| **Approach-type signal** | What kind of idea you'll extract | See categories below — a rule-based agent teaches you decision heuristics; a meta/replay-analysis notebook teaches you *what to build*, not how; a "beating X bot" notebook teaches you a specific exploit. |
| **Specificity of claim** | Trustworthiness | "Beating the Day-1 #1 Crustle Bot" or "75% WR vs my 1300+ Starmie" (`masamikobayashi/a-sample-archaludon-75-wr-vs-my-1300-starmie`) makes a falsifiable claim against a named opponent — easier to verify locally via `run-battle` than a vague "improved agent." |

## Approach-type categories seen in the actual kernel list

- **Official rule-based samples per archetype** (Kiyota's series: Mega Lucario ex, Dragapult ex,
  Iono's, Mega Abomasnow ex) — highest votes, likely the competition's own baseline templates.
  Read these first; they define the observation/action interface idioms everyone else builds on.
- **RL / search-based** (`kiyotah/reinforcement-learning-and-mcts-sample-code`,
  `abiolatti/custom-engine-with-vectorized-env-2m-sample-sec`, `yukaika/pok-mon-tcg-deck-transformer-training`) —
  higher ceiling, higher setup cost. Only worth the time if Days 3-4 leave room for it.
- **Meta / replay analysis** (`pilkwang`/`biohack44`/`makthanithin`'s meta-snapshots,
  `smallpond/en-replay-archetype-analysis`, `myso1987/ptcg-ai-battle-leaderboard-deck-meta-by-score-band`,
  `busyaprime/what-actually-wins-on-the-ladder`) — read these for *what to build*, not code to reuse.
  `busyaprime`'s title in particular is exactly the question this whole research phase is asking.
- **Anti-meta / matchup-specific** (`dashimaki360/beating-the-day-1-1-crustle-bot`,
  `kokinnwakashuu/ptcg-lucario-public-lab-anti-crustle-log`) — confirms Crustle as a named, recurring
  threat worth explicitly testing the candidate deck against, not just the bundled random baseline.
- **Tooling** (replay viewers, deck image renderers, card-list viewers, local battle JSON output) —
  skip auditing these for strategy; only pull one if a specific tooling gap blocks Days 3-7.

## Practical rule

Spend Day 1-2 audit time in this order: official rule-based samples → the highest disclosed-LB-score
kernel → the most recent meta-snapshot → 1-2 anti-meta notebooks (Crustle matchup) → RL/search sample
only if time remains. Log the decision (audited vs skipped, and why) in each entry of
`notebook-audit-template.md` so it's clear what was deliberately deprioritized under the 10-day budget.
