# Top-score notebook research — PTCG AI Battle

Consolidated report per the `kaggle-competition-playbook` skill's intel-gathering format.
No `kaggle-competition-intel` MCP server is installed in this environment, so this used the
documented fallback: manual Kaggle CLI (`kaggle kernels list`, `kaggle competitions
leaderboard`) plus a user-provided screenshot of Kaggle's Code-tab UI, which shows a
per-notebook "Score" badge that the CLI/API does not expose and that a plain `WebFetch` cannot
render (the Discussion/Code tabs are a JS-rendered SPA — confirmed empty on direct fetch).

Per `information-sharing-policy.md`: all sources below are notebooks their own authors
already made public on Kaggle, cited here with author + URL as scouting-signal research notes
for our own private workspace — not re-published or copied wholesale. Code was read for ideas
and, where explicitly permitted or itself an official/public sample, rebuilt locally; nothing
here bypasses a license or the competition's own sharing rules.

## Competition & metric

- **Slug**: `pokemon-tcg-ai-battle` — "The Pokémon Company - PTCG AI Battle Challenge
  Simulation" (Simulation ladder track; a separate Strategy track exists at
  `pokemon-tcg-ai-battle-challenge-strategy`, ends later).
- **Metric**: TrueSkill-style rating N(μ, σ²) per team, updated per episode on **win/loss/draw
  only** — margin and speed don't affect it. Submission format: `main.py` (exposing
  `agent(obs_dict) -> list[int]`) + `deck.csv` (60 card IDs) + the competition's `cg` engine,
  packaged as `submission.tar.gz` and uploaded directly (`kaggle competitions submit`) — not a
  kernel-linked code competition, direct file upload is the correct and only method used by
  every source found, including official samples.
- **Constraints**: 5 uploads/team/day; only 2 Final Submissions count for placement and must be
  manually selected (auto-select picks your latest two, not your best two).
- **Live leaderboard top** (checked 2026-08-07): **~1202** (team LiamK); next tier ~1100-1145.

## Score-ranked notebooks found

Two different kinds of "score" appear across sources — flagged per row since conflating them
was an early mistake worth not repeating:

| Notebook | Author | Score | Votes | Last run | Score type | URL |
|---|---|---:|---:|---|---|---|
| Max Elo: 1208, LibraryOut w/ Crustle & Great Tusk | soutasakurai | **1208** | 10 | 2026-06-26 | self-reported title, **author states it's from a former/different submission, not guaranteed reproducible by this exact shared code** | kaggle.com/code/soutasakurai/max-elo-1208-libraryout-w-crustle-great-tusk |
| (private, unshared) Starmie/Froslass, "Gold Medal range" | masamikobayashi | **"1300+"** | — | — | self-reported, **no code shared** (only a reusable `PrizeTracker` helper) — cannot verify | n/a (referenced from a different public notebook) |
| Meta Snapshot: 07-July (forked from Nithin maktha) | biohack44 | 947.5 | 137 | ~1mo ago | Kaggle Code-tab author-score badge (screenshot) — likely the author's current overall leaderboard score, not literally this notebook's own output | kaggle.com/code/biohack44/pok-mon-tcg-ai-battle-meta-snapshot-07-july |
| Probablity v2 | aristophanivan | 933.8 | 70 | ~1mo ago | Code-tab author-score badge | kaggle.com/code/aristophanivan/probablity-v2 |
| [STRONG START]: Baseline Agent V10 \| LB 950+ | romanrozen | 865.5 (badge) / "950+" (title) | 185 | 3d ago | Code-tab badge shows 865.5, title claims 950+ — consistent with μ drifting down from an earlier peak reading | kaggle.com/code/romanrozen/strong-start-baseline-agent-v10-lb-950 |
| PTCG Meta A Stable Submit | llccqq624 | 864.6 | 31 | ~1mo ago | Code-tab badge. **Code is a byte-identical re-share of masamikobayashi's Archaludon/Cinderace agent** | kaggle.com/code/llccqq624/ptcg-meta-a-stable-submit |
| Pokemon AI Battle Agent: Mega Lucario | nursrijan | 851.5 | 49 | 2mo ago | Code-tab badge | kaggle.com/code/nursrijan/pokemon-ai-battle-agent-mega-lucario |
| BattleCore Compact Agent | lucifer19 | 846.8 | 27 | ~1mo ago | Code-tab badge | kaggle.com/code/lucifer19/battlecore-compact-agent |
| Codex Sol Eclipse Alakazam | jazivxt | 840.3 | 55 | 8d ago | Code-tab badge | kaggle.com/code/jazivxt/codex-sol-eclipse-alakazam |
| MultiPly Agent. Best: 940 LB | aristophanivan | "940" | 51 | — | self-reported title | kaggle.com/code/aristophanivan/multiply-agent-best-940-lb |
| Pokemon TCG AI Battle - 1084.5 Baseline | makthanithin | "1084.5" | 26 | — | self-reported title | kaggle.com/code/makthanithin/pokemon-tcg-ai-battle-1084-5-baseline |
| A Sample Archaludon: 75% WR vs my 1300+ Starmie | masamikobayashi | none disclosed (never submitted by author) | 96 | 2026-06-27 | n/a — but see cross-validation below | kaggle.com/code/masamikobayashi/a-sample-archaludon-75-wr-vs-my-1300-starmie |

**Our own real, verified scores** (this repo's actual submissions, ground truth rather than
any notebook's claim):

| Our submission | Source notebook | Real μ (Kaggle-scored) |
|---|---|---|
| `submissions/kiyota_mega_lucario_ex` | kiyotah's official Mega Lucario ex sample | **439.9-450.9** (2 readings) |
| `submissions/masamikobayashi_archaludon_cinderace` | masamikobayashi's Archaludon/Cinderace sample | PENDING (ref `55308121`, submitted 2026-08-06) |

**External, non-Kaggle source**: `TomBombadyl/kaggle_pokemon` (public GitHub repo, no Kaggle
notebook) — real ladder logs showing their own Archaludon ex/Cinderace + "R7 empty-bench guard"
agent scored **1196.1-1224.2 μ** (2026-06-28), the single strongest *verified-real* number found
anywhere in this research.

## Common technique themes

1. **Archaludon ex / Cinderace / Duraludon / Relicanth is the community-converged top
   archetype** — independently arrived at by 4 sources: TomBombadyl (private ladder testing),
   masamikobayashi (original public sample), llccqq624 (re-shares it as "stable meta_a"), and
   lucifer19 (ships it as their primary "Profile A" after a rigorous ~20,000-game validation).
   This is the strongest convergent signal in the whole research effort.
2. **Rule-based scoring over legal options, not ML.** Every agent found — from the official
   Kiyota samples through the highest-scoring community ones — is a hand-tuned scorer: assign
   each legal option a numeric priority, pick the highest. No shipped agent in any source beat a
   well-tuned rule-based one with RL/MCTS/learned approaches (see `baseline-comparison.md`'s
   original TomBombadyl findings — reconfirmed here, nothing found today contradicts it).
3. **Matchup-specific overrides on top of a generic scorer** is the pattern that separates
   "intermediate/official sample" tier (our first submission, ~440μ) from "community-tuned" tier
   (masamikobayashi's Crustle/Alakazam/Hop/Lucario-specific logic, grid-searched thresholds).
4. **Imperfect-information deck inference matters for search-based finishing lines** —
   masamikobayashi's shared `PrizeTracker` (subtract every visible card from the known decklist;
   only trust the remainder as "prized" when the count exactly matches `len(player.prize)`;
   explicitly handle in-flight effect cards via `obs.select.effect`) is a reusable, freely-shared
   component for anyone adding a Forward-Search "can I win this turn?" mode.
5. **A different win condition exists and works, at least locally**: soutasakurai's Great
   Tusk/Crustle library-out (mill) deck beat our own submitted Archaludon 80% of 20 local games —
   a real alternative axis, not just "which attacker deck," though carrying real caveats (see
   below).
6. **Defensive packaging habits worth adopting** (all now in use in this repo): validate
   `{"main.py", "deck.csv", "cg/api.py", "cg/libcg.so"}` exist in the built tar before
   considering it submit-ready (makthanithin); `py_compile.compile("main.py", doraise=True)`
   before packaging to catch syntax errors for free (llccqq624); guard any `__file__` use with
   `try/except NameError` since Kaggle executes `main.py` via `exec()` with no `__file__` in
   scope (learned the hard way from our own first submission's ERROR, independently confirmed
   as the standard pattern in every well-engineered sample found afterward).

## Ideas worth testing locally

- **Soutasakurai's Great Tusk/Crustle library-out deck** — already built and tested
  (`submissions/soutasakurai_libraryout_crustle/`), 80% WR vs our Archaludon baseline, 95% vs
  Lucario. Real candidate for a next submission, pending a decision on spending a daily slot
  (see open question in `baseline-comparison.md`).
- **`PrizeTracker` component** — worth integrating once we build any search/lethal-detection
  logic on top of the Archaludon baseline.
- **lucifer19's "sham-search placebo control"** — a concrete pattern for sanity-checking our own
  `run-battle` local test harness itself (not just the agent under test) if a local result ever
  looks suspiciously strong, to rule out arena/harness contamination rather than trusting the
  number outright.
- **myso1987's leaderboard-deck-meta-by-score-band scraper** — not yet run (multi-hour for full
  mode), would give a real current archetype-prevalence-by-score-band answer instead of
  inferring meta from kernel titles. Candidate for the Day-8 late-meta check in `10-day-plan.md`.

## Ideas that look risky

- **soutasakurai's 1208 title claim** — by the author's own admission, from a different
  submission than the shared code; do not treat the shared main.py as guaranteed to reach 1208.
  Our 80%-vs-Archaludon local result is real and independently encouraging, but it's a narrow
  2-opponent test, and the deck's own documented weakness (vs a fully-set-up Lucario) and
  self-deck-out risk aren't exercised by that test.
- **Any Kaggle "Score" badge inferred from a screenshot** — most likely each author's *current
  overall leaderboard score* shown as context next to their notebook, not literally "this
  notebook scores X when run as a submission." Treat as directional evidence about the
  author's general skill level / a rough score band for their techniques, not a precise,
  attributable number for that specific shared code.
- **Any self-reported title score in general** — confirmed twice now in this repo's own
  experience that a fresh submission's first μ reading is unstable, and per the generic
  `01-competition-patterns.md` score-stabilization pattern, scores can take hours to settle.
  A title written once, possibly weeks ago, is not necessarily still accurate even if it was
  accurate then.

## See also

- `notebook-audit-template.md` — full per-kernel audit entries (more detail than the summary
  table above).
- `baseline-comparison.md` — the actual baseline decision history and open next-step question.
- `10-day-plan.md` — the execution roadmap and submission log with real μ readings.
