# Discussion-forum intel report — PTCG AI Battle

Consolidated per the `kaggle-competition-playbook` skill's intel-gathering format, covering the
**Discussion tab** (the Code/notebook tab is covered separately by the main checkout's
`notebooks/kaggle-research/top-scores-report.md`). For pre-submission evaluation methodology
specifically (how competitors judge agent quality locally given LB noise), see the narrower
companion report `evaluation-methodology.md`.

## Sourcing method

No `kaggle-competition-intel` MCP server is installed in this environment. Rather than falling
back to the documented manual-CLI/screenshot path, this used the **Kaggle CLI's `topics`
subcommand** directly, which turned out to give more complete data than the MCP tool would:

- `kaggle competitions topics list pokemon-tcg-ai-battle --format json` — paginated via
  `--page-token` (token is printed as trailing text after the JSON array, stripped before
  parsing) until an empty page. **204 total discussion topics** retrieved, deduplicated by id.
- `kaggle competitions topics show <id> --format json` — full comment tree per topic (author,
  votes, date, HTML body) for a **58-topic subset**: top 15 by vote count, top 15 by post date
  (most recent), plus every topic whose title flagged a rule clarification, leaderboard/scoring
  issue, or bug report, regardless of vote count.
- Hit Kaggle's API rate limit (`429`) partway through the 58-topic pull; retried with backoff,
  all 58 eventually succeeded.

**Known gap**: the CLI's `topics show` does not expose the *original post body* — only topic
metadata (title/author/votes/date) plus the comment thread. For low-comment topics (e.g.
`733477 Game engine bug`, 0 comments as of this pull) there is effectively no content beyond the
title. Summaries below are built from the comment threads, which usually restate or quote enough
of the original post to reconstruct it, but treat zero/low-comment topics as "title only, watch
for replies."

Per `information-sharing-policy.md`: content below paraphrases public forum posts for internal
scouting use, attributed by username where relevant; no private strategy or non-public data is
included.

## Competition context

- Slug: `pokemon-tcg-ai-battle` ("The Pokémon Company – PTCG AI Battle Challenge Simulation").
  Separate Strategy track: `pokemon-tcg-ai-battle-challenge-strategy` (deadline 2026-09-13,
  $240,000 prize pool, top 8 advance to an in-person Second Round in Tokyo).
- Simulation submission deadline: **2026-08-16 23:59 UTC** (locks further submissions). Games
  continue ~2 more weeks (through ~2026-08-31) until the leaderboard "converges" before final
  ranking — confirmed directly by host `shige` in `Second Round Information` (#732331).
- Report pulled 2026-08-07.

## Top-voted threads

| Votes | ID | Title | Comments | Date |
|---|---|---|---|---|
| 124 | 717141 | Game Engine Source Code | 11 | 2026-07-01 |
| 102 | 711737 | Request for an explicit ruling on game engine source, reverse engineering, and community engine | 22 | 2026-06-21 |
| 77 | 712621 | Leaderboard Scoring Inconsistency | 23 | 2026-06-23 |
| 74 | 709160 | Daily Top Episodes Datasets | 5 | 2026-06-17 |
| 74 | 724362 | Top players' methods, revealed by 30,000 games | 12 | 2026-07-10 |
| 58 | 712657 | Is Battle Simulate Matching Process Working Well? | 7 | 2026-06-23 |
| 56 | 729926 | Tracking 3,057 teams through 6 weeks of meta | 15 | 2026-07-27 |
| 51 | 709494 | [For First-Timers] Kaggle Rules You Should Know | 10 | 2026-06-18 |
| 41 | 716045 | June 30 Update: Updated Simulation Environment, gameplay increases | 9 | 2026-06-30 |
| 39 | 717697 | Sharing my Reinforcement Learning journey (updated) | 55 | 2026-07-02 |
| 39 | 708869 | Is there a way to view the visualizer without submitting? | 6 | 2026-06-17 |
| 36 | 708586 | Differences Between the Official Rules and the Simulator Behavior | 27 | 2026-06-16 |

(All URLs: `https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/<id>`)

**#717141 / #711737 — Engine source code release.** The community pushed hard (711737, 102
votes, 22 comments) for an explicit ruling on reverse-engineering vs. an official source release,
after the host initially asked for time to decide internally. Host (`shige`) ultimately released
`ptcg_engine.zip` (717141). Permitted use, per host reply: code *derived from or compiled from*
the released engine is fine in submissions, but Pokémon Elements (cards/engine) or models trained
on them can't be used outside the competition or commercially; winners grant the sponsor a
license. A community reply in 717141 reports a suspected bug in `ToolCountProc` (variable
shadowing in the Team-Rocket-only-Energy discard routine) that a losing player could deliberately
trigger to crash the engine — unresolved in the captured thread, worth defending against rather
than exploiting (host separately said engine "hacks" can be patched and ruled unfair). ARM64
binaries were requested but not confirmed as delivered.

**#712621 — Leaderboard Scoring Inconsistency.** The single biggest complaint thread. Multiple
participants report the *same or near-identical agent* landing at wildly different ratings
(e.g., 800s vs. 1100+) even after ~1 day active, because match volume is low early on and the
first handful of games dominate the rating. Consensus: this discourages people from resubmitting
improved agents (fear of "re-rolling" the early lottery), which keeps the visible meta static.
Directly tied to #726690 (systematic per-hour episode-rate disparity between submissions —
~2.4 vs. 14–24 episodes/hour observed) and #733083/#732905 (same agent submitted twice landing
300–400+ rating points apart). Community-recommended workaround: wait 1–2 days before trusting a
score, longer than this repo's existing "4 hours" guidance in `top-scores-report.md` — worth
tightening that number.

**#732105 — Alternative PTCG Rankings.** Proposes replacing sequential Elo/TrueSkill with a
Bradley–Terry fit over the whole match history (order-independent, matches Kaggle's own recent
"Kaggriculture" competition). A quoted host comment ("mid-competition rule changes would be too
disruptive") suggests this won't change this cycle — treat current scoring volatility as
permanent for this competition, not a bug that gets fixed.

**#709160 / #729926 — Data and meta tracking.** Host publishes daily "top episodes" datasets
(rated by highest average participant rating, biasing toward top competitors). Community analysis
of 3,057 teams over 6 weeks (729926) found teams switch decks/strategies too late relative to
meta shifts, and top performers deliberately cycle strategies off the leaderboard quickly (~1 day
visible) specifically to avoid being studied and countered.

**#724362 / #717697 — Technique mix.** Leaderboard is a mix of rule-based/heuristic-search,
tree/MCTS search, and RL (PPO); some agents that look rule-based from the outside are actually
RL+search. Reported RL training scale: ~45 games/sec self-play, ~a day of GPU training ≈ 3–5M
games of experience, still described by its own author as "undertrained." By late July, community
consensus (#728168) is that pure rule-based agents cap out around top 10–20 at best; the Gold
tier is now dominated by model-based (RL/imitation) agents.

## Most-recent threads (by post date, as of 2026-08-07)

| Date | ID | Title | Votes | Comments |
|---|---|---|---|---|
| 08-07 | 733477 | Game engine bug | 0 | 0 (no content yet) |
| 08-06 | 733267 | Shaymin vs Battle Cage | 2 | 3 |
| 08-06 | 733265 | [Bug] Simulator switch the deck between players | 1 | 0 (no content yet) |
| 08-06 | 733137 | Timing of solution sharing after the deadline | 5 | 0 (no content yet) |
| 08-05 | 733083 | ELO inconsistency | 1 | 8 |
| 08-05 | 732905 | How consistent is imitation learning in this setting? | 4 | 9 |
| 08-04 | 732665 | Using current time in submission for strategy? | 1 | 0 |
| 08-03 | 732502 | Unable to load episode replay (Too many requests) | 1 | 4 |
| 08-03 | 732469 | Official replay viewer is currently unreachable | 6 | 1 |
| 08-02 | 732331 | Second Round Information | 23 | 18 |
| 08-02 | 732167 | Is getting a gold mandatory for becoming a finalist in the strategy competition? | 0 | 4 |
| 08-01 | 732105 | Alternative PTCG Rankings | 21 | 5 |

Note: "most recent" here = most recently *created* topic (the CLI only exposes topic post date,
not last-reply date) — several older threads (e.g. #712621, #726690) are still actively
accumulating replies and would rank higher under a last-activity sort.

**Newest open items** (no host resolution captured yet, worth revisiting): #733477 (engine bug,
no detail), #733265 (bug: simulator reportedly swaps decks between players), #733137 (asking when
strategy write-ups may be shared after the Aug 16 deadline).

**#732502 / #732469 — Replay/visualizer infrastructure strain.** Episode-replay fetching and the
official visualizer hit rate limits / went briefly unreachable in early August; one user reports
downloading 4,700+ "gold" replays over 5 days via notebook before hitting the limit. Host-adjacent
guidance: rate-limit window is under an hour; use the official bulk dataset
(`kaggle/pokemon-tcg-ai-battle-episodes-index`) instead of per-episode fetches for training data.

**#732331 — Second Round Information** (host `shige`, direct answers): Second Round is in-person
in Tokyo; strategy-track results do **not** affect the final Simulation leaderboard; teams may use
a different deck/agent in the Second Round than their First Round submission; no additional
restrictions beyond First Round rules. Travel/accommodation support details go out directly to
qualifying teams, not published publicly.

## Rule/engine-risk threads (flagged regardless of vote count)

- **#708586 — Differences Between Official Rules and Simulator Behavior** (36 votes, 27
  comments): general Q&A on simulator semantics. Confirmed: `ABILITY` options are explicit
  selectable actions; `SKILL` entries are passive/continuous effects (e.g. Clefairy-style) that
  auto-apply and don't need re-selection via `Options[]` each turn. One unresolved report:
  during setup, if you have a spare Basic in hand after choosing your Active, the option list
  doesn't offer an explicit "end turn" — forcing the agent to bench all Basics in hand (unclear
  if intended).
- **#708766 — Japanese vs. English rulebook disparity**: engine is implemented against the
  **Japanese** ruleset; where Japanese/English rulings differ, the engine follows Japanese rules
  — confirmed by host `shige`.
- **#711381 — Card pool format**: a custom Standard-based pool defined specifically for this
  tournament, not identical to the current in-person format; fixed for the tournament's duration
  unless a rebalance is needed.
- **#709320 / #708979 / #709598 / #709596 — External data / sharing rules** (host `Addison
  Howard`, authoritative): self-collected data (playing games yourself/with friends and recording
  results) is fine, including using logs from other participants' *public* matches; purchasing a
  costly external dataset is not ("Reasonableness Standard" targets cost-prohibitive datasets
  specifically, not cheap subscriptions); data from friends who *won't* make it public during the
  competition is a explicit grey area the host called "icky" and discouraged. Private sharing =
  sharing a notebook/strategy with someone specifically to entice a team-up; publicly discussing
  willingness to team up is fine.
- **#709545 — Unfair playing practices**: legitimate strategic tactics are fine; exploiting the
  game engine (a "hack") is not, and the host reserves the right to patch it — relevant given the
  #717141 crash-bug report above.
- **Confirmed/resolved bug reports**: #709895 (player attacking on "their" turn 1 — was actually
  the *opponent's* turn 1 after the reporter's own agent instantly passed; not an engine bug),
  #712226 (Mirage Barrage discard-count report — host couldn't reproduce, reporter retracted),
  #714920 (deck-search "blindness" — not a bug: card objects live in `observation.select.deck`,
  indexed by `option.index`, just not inline in the option list itself).
- **Open/unconfirmed bug reports** (no host resolution captured in this pull): #716241 (Rare
  Candy consumed without evolving when Active was hit by Evolution Jammer the prior turn — the
  Rare Candy evolve path doesn't hide the option the way the normal evolve menu does),
  #717141's off-by-one visualizer replay indexing report, #730707 (a submission was rejected
  without error detail because `obs.current` was `null` during the coin-toss/setup phase and the
  agent's own exception handler silently returned the full deck list as its "action" — a defensive
  coding lesson for our own agent as much as an engine issue), #728287 ("Player 1's deck error" at
  step 0 despite a mathematically valid 60-card deck), #733265 (deck-swap-between-players report,
  posted 08-06, no replies yet).
- **#714575 — Card data CSV naming**: `EN_Card_Data.csv` has slightly wrong energy names
  ("Telepath(ic) Psychic Energy", "Rock(y) Fighting Energy") vs. the printed card — matters if
  matching by name rather than ID.
- **Compute/runtime constraints** (#708810, host `Bovard Doerschuk-Tiberi`): 600 seconds **total**
  per game per team (no per-turn increment), CPU-only inference, 1.6 vCPUs, 8GB RAM, same Python
  packages as the standard Kaggle notebook environment (check the `kaggle-environments` repo's
  Dockerfile for exact versions).
- **#716045 — June 30 official update**: target raised to 48 matches/day/submission, plus a 10%
  chance of being matched against a random opponent (explicitly to fight meta staleness). A "won
  but +0 rating" report was confirmed expected behavior when the skill gap is large enough.

## Technique & meta signals

- **Imitation learning** (#732905, #733083): reported policy-accuracy figures cluster 70–90%
  depending on data volume/method; one participant found conditioning the model on the recorded
  player's ELO gives a further ~2% accuracy bump and extrapolates somewhat to higher ELO targets.
  Consistency between submissions of the *same* trained agent is a widely-reported pain point —
  differences of 300+ rating points have been observed, generally attributed to early-game
  matchup variance rather than the model itself, per the Leaderboard Scoring Inconsistency thread.
- **RL approaches** (#717697, 55 comments — the most-discussed single thread): PPO-based
  self-play is a common approach; participants report search (MCTS-style) helping less than
  expected in this game because it's imperfect-information with high uncertainty and a weak value
  head doesn't help search discriminate action quality — one author explicitly abandoned search
  for that reason.
- **Deck/meta dynamics** (#729926, #731739): Grimmsnarl/Froslass rose to leaderboard prominence
  partly because it's the deck most imitation-learning bots default to well (over-represented in
  the training replay pool) and has favorable matchups into Alakazam/Crustle, which were early
  top-meta decks. Dragapult ("Crushing Hammers" variant) is a strong but underused counter, likely
  because its coin-flip-dependent lines add training/implementation complexity. Multiple
  participants note human-tournament matchup data (limitlesstcg) diverges meaningfully from the
  Kaggle-agent meta — optimizing for human play does not transfer directly to optimizing for the
  agent field.
- **Rule-based agents** (#728168): were competitive (top 10) early in the competition; by late
  July, community self-report puts a well-tuned pure-heuristic agent around 880±20 and outside
  the top 200, with the Gold tier now dominated by model-based agents.

## Open questions / things to watch

- **#733137 — Timing of solution sharing after the deadline** (posted 08-06, no answer yet):
  relevant to when this repo can safely go public or share write-ups; check for a host reply
  before the Aug 16 deadline.
- **#733265 / #733477 / #728287 — Unresolved bug reports**, all still open as of this pull; worth
  a follow-up check closer to the deadline in case they turn into confirmed engine patches that
  change behavior we depend on.
- **Scoring volatility is not going to be fixed this cycle** (per the quoted host comment in
  #732105) — treat current-score noise as a permanent property of this competition, not a
  transient bug; budget 1–2 days of stability time after each submission before trusting its
  rating, more conservative than this repo's existing "under 4 hours" guidance.
- **Public Notebook Sharing Deadline was 2026-08-02** (#728935, title/date only, full thread not
  pulled in this batch) — already passed as of this report; check whether it changes what's safe
  to scout going forward.

## Implications for our agent

Cross-checked against the current state in the main checkout: working baseline is
`submissions/masamikobayashi_archaludon_cinderace/main.py` (ref `55308121`, rule-based
Archaludon ex/Cinderace, no training), plan in `10-day-plan.md`, archetype/agent evidence in
`baseline-comparison.md`. What this discussion pull changes or confirms about that plan:

1. **Strategic risk to flag, not yet in the plan**: #728168 ("What is your highest score for an
   active rule-based agent") puts pure rule-based agents outside the top ~200 by late July, with
   Gold tier dominated by RL/imitation agents. `baseline-comparison.md`'s own evidence (every
   trained approach TomBombadyl shipped lost to rules) supports staying rule-based for now, but
   this discussion thread is an independent, more recent (07-22) signal pointing the other way.
   With ~9 days left to the 08-16 deadline, this is worth an explicit go/no-go check rather than
   assuming "reach for ML only after the rule-based ceiling is clear" (`baseline-comparison.md`
   recommendation 5) still holds — the ceiling may already be lower than earlier evidence implied.
2. **Tighten the score-stabilization wait time.** `10-day-plan.md`/`baseline-comparison.md`
   already say "don't trust the first reading," but #712621/#733083/#732905 give a harder number:
   same-agent resubmissions have landed 300+ rating points apart even after ~1 day active, and
   the community's practical rule is 1-2 days, not hours. Update the "≥2 stable μ readings" advice
   in `baseline-comparison.md` recommendation 1 to explicitly wait 24-48h, not just "more than
   one reading."
3. **Correctness-guard checklist, three new entries** (extends the existing "never leave the
   bench empty" guard already identified as the highest-value fix in `baseline-comparison.md`):
   - Never let a broad `except` branch return `read_deck_csv()` (the full deck list) in response
     to a mid-game action prompt — #730707's submission was rejected without explicit error
     because `obs.current` was `null` during the coin-toss/setup phase, an exception fired, and
     the catch-all returned the deck-submission response instead of a legal option index. Checked
     the current baseline: `agent()` at `main.py:1083-1096` only returns `read_deck_csv()` when
     `obs.select is None` (the actual deck-submission phase) and falls back to a random legal
     option on any other exception (line 1095-1096) — this specific trap is already avoided, but
     worth a regression test (`run-battle` with a forced early-exception) given how easy it is to
     reintroduce.
   - Deck-search options (`select.deck`) and the `ABILITY` vs `SKILL` option-type distinction
     from #708586/#714920 are already handled correctly (`main.py:143-144`, `:859`) — no action
     needed, just confirms the current implementation matches the community's understanding of
     the API, not a coincidence worth re-deriving from scratch.
   - Two open, unresolved engine bug reports worth a pre-submission sanity check on Day 9
     (`10-day-plan.md`'s hardening day): #716241 (Rare Candy consumed without evolving after
     being hit by Evolution Jammer) and #733265 (simulator allegedly swapping decks between
     players, reported 08-06, no host reply yet) — neither confirmed as real bugs, but cheap to
     grep the current deck/evolution logic for exposure before the deadline locks submissions.
4. **Deck/meta signal is a caution, not a redirect.** #729926/#731739 explain *why* Grimmsnarl/
   Froslass looks dominant on the public leaderboard (imitation-learning bots default to it
   because it's over-represented in the training replay pool, not because it's intrinsically
   strongest) — this is a reason to trust `baseline-comparison.md`'s Archaludon evidence (5
   independent sources, 62.2% score rate over 1725 real games) over chasing the visible-leaderboard
   meta, not a reason to switch decks.
5. **Submission-rate variance context.** #712621/#726690/#731933's reports of highly uneven
   episodes/hour by score band explain why `10-day-plan.md`'s submission log shows some refs
   sitting at "PENDING" for 40+ minutes with few games — this is a documented, host-unaddressed
   platform characteristic, not a sign something is broken with our submission specifically.
6. **Missing from the current plan**: the Strategy competition track
   (`pokemon-tcg-ai-battle-challenge-strategy`, deadline 2026-09-13, separate $240,000 prize pool,
   top 8 advance to an in-person Second Round in Tokyo per #732331) isn't mentioned anywhere in
   `10-day-plan.md`, which only tracks the Simulation deadline. Worth a deliberate decision on
   whether to pursue it after 08-16, not an oversight to catch later.
