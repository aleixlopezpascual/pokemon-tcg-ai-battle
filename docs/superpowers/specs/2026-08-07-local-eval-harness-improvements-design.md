# Local eval harness improvements — design

## Context

`src/local_eval.py` pools a candidate agent's win rate across a fixed 4-agent local roster
(random baseline + our 3 real submissions) with Wilson 95% confidence intervals. It's already
been calibrated against real ladder scores (`notebooks/kaggle-research/baseline-comparison.md`):
it correctly flags obviously-weak candidates, but it inverted the ranking between two
comparable-strength candidates (Great Tusk 73.3% local vs 65.0% for Archaludon, while the real
ladder ranked Archaludon higher) — so it's a pre-submission sanity gate, not a way to pick a
winner between similar candidates.

A discussion-forum research pass (`notebooks/kaggle-research/evaluation-methodology.md`) mined
204 Kaggle discussion topics for how other competitors evaluate agents locally, and found the
same failure mode independently reported by multiple participants, plus three concrete practices
we don't currently do:

1. **Opponent pool too narrow.** Our roster is 4 same-tier rule-based agents (well, 3 rule-based
   + random). Jake (`discussion #717697`) diagnosed the exact same local/ladder divergence and
   fixed it by growing the pool from 3 to 9 decks, mixing 6 learned agents with 3 rule-based ones.
2. **No replay/failure detail captured.** We only count wins/errors in aggregate. Abhyuday
   (same thread) explicitly credits "pulling replays and doing data analysis" per losing matchup
   as how he diagnosed why a strong-on-paper agent was actually losing.
3. **No stability check on the readings themselves.** djschmit (`discussion #712621`) ran a
   20,000-match local study specifically to measure how match-count/format affects ranking
   stability. We've never checked whether our fixed 30-games-per-matchup default is enough to
   avoid a matchup's win rate flipping between runs.

This design closes all three gaps in `src/local_eval.py`, reusing engine capability already
present in the codebase's own research: the pulled kernel
`notebooks/kaggle-research/pulled/kiyotah__how-to-output-local-battle-as-json-and-view/` shows
`cg.game.visualize_data()` produces a JSON replay consumable by the community's existing
`visualizer.html` (which posts to the official `ptcgvis.heroz.jp` viewer) — no new infrastructure
needed for replay capture.

## Goals / non-goals

- Goal: make `local_eval.py` a better pre-submission filter and a better *diagnostic* tool,
  without pretending it can replace a real ladder reading (it still can't — see the calibration
  caveat above, which this design doesn't try to fix, only work around).
- Goal: every change is opt-in or additive — default invocation (`--candidate X`) keeps working
  exactly as today, just with one more opponent in the roster.
- Non-goal: porting new opponent agents from `notebooks/kaggle-research/pulled/` kernels that
  aren't already runnable submissions. That's real audit/adaptation work, out of scope for this
  pass — flagged as a natural follow-up, not silently dropped.
- Non-goal: touching the real Kaggle submission format, `main.py` correctness guards, or deck
  choice. This is purely a local-tooling change.

## Design

### 1. Expand `DEFAULT_OPPONENTS` (4 → 5)

Add `submissions/il_agent_v2b` to the list in `src/local_eval.py`. It's the current,
Kaggle-safe imitation-learning candidate (dependency-free `pure_predictor` export, per
`CLAUDE.md`'s documented pattern) playing a Grimmsnarl ex/Froslass deck mined from real training
data — a different archetype *and* a different technique (trained model vs. hand-tuned rules)
from the other three opponents. `il_agent_v1` is excluded (confirmed buggy: always returns
`maxCount` options regardless of what's actually wanted, and ships an Archaludon deck that barely
appears in its own training data — not a useful sparring partner). `il_agent_v2` is excluded as
a near-duplicate of `v2b` (same policy, same deck, only the model-export format differs) that
would dilute rather than diversify the pool.

This is a one-line addition to the existing list — no new code path.

### 2. Replay capture on candidate losses (`--save-losses DIR`)

New optional CLI flag, default off (`None` — no behavior change if omitted).

`run_matchup` gains an `save_losses_dir: Path | None` parameter. When set:

- Before each battle's action loop, initialize `obs_log = [""]` and `action_log = [None]`
  (matching the pulled kernel's exact convention, since `visualize_data()`'s output is indexed
  against these).
- Inside the loop, after computing `select_list` and before calling `battle_select`, do
  `obs.pop("search_begin_input", None)` (the pulled kernel does this unconditionally; using
  `.pop(..., None)` instead of a bare `.pop(...)` since not every observation is guaranteed to
  carry that key), then append the popped-clean `obs` and `select_list` to their logs.
- After the battle loop ends (winner known) but **before** calling `battle_finish()` — the
  pulled kernel confirms `visualize_data()` must run while the battle is still live — if
  `winner_is_candidate` is `False`, call `vis = json.loads(visualize_data())`, merge in
  `obs`/`action` per step exactly as the reference kernel does
  (`vis[i]["obs"] = obs_log[i]`, `vis[i]["action"] = [action_log[i], action_log[i]]`), and write
  it to `save_losses_dir / f"{opponent_dir.name}_battle{i}.json"`.
- `visualize_data` is imported from `cg.game` alongside the existing `battle_start`,
  `battle_select`, `battle_finish` import.

Output files are directly compatible with the existing `visualizer.html` pattern documented in
`notebooks/kaggle-research/pulled/kiyotah__how-to-output-local-battle-as-json-and-view/` — no new
viewer needed, just point it at a saved loss file.

### 3. Stability check (`--repeats N`)

New optional CLI flag, default `1` (no behavior change at the default).

In `main()`, when `--repeats N` with `N > 1`: for each opponent, call `run_matchup` N independent
times at the existing `--battles` count, producing N `(wins, games)` pairs. Compute:

- Each repeat's own Wilson CI.
- Whether all repeats' point estimates fall inside every other repeat's CI. If not, mark that
  opponent row `UNSTABLE` in the printed report — a concrete, actionable signal to either bump
  `--battles` for that matchup or treat its current reading with more skepticism.
- The pooled result across all N×battles games as the reported aggregate (more data than any
  single repeat, tightening the final CI) — this is a strict improvement over today's
  single-pass aggregate, not just a diagnostic side-channel.

At the default `--repeats 1` this block is skipped entirely and output is byte-for-byte identical
to today's.

## Testing / verification

- This worktree lacks `submissions/` and `data/raw/` (gitignored, not present outside the main
  checkout) — copy the needed directories from the main checkout (`/Users/aleix.lopez/pokemon-tcg-ai-battle/submissions`,
  `/Users/aleix.lopez/pokemon-tcg-ai-battle/data/raw`) into this worktree before testing. Purely
  local dev assets, not committed either place.
- Run `python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace`
  with no new flags — confirm output is identical in shape to before (now 5 rows instead of 4).
- Run the same with `--save-losses /tmp/losses` against a candidate expected to lose at least
  once (e.g. against `il_agent_v2b` or the strongest rule-based opponent) — confirm at least one
  JSON file is written and is loadable by `visualizer.html`'s expected schema (a list of
  per-step dicts with `obs`/`action` keys).
- Run with `--repeats 3 --battles 10` — confirm three repeats print, pooled aggregate uses all
  30 games, and an intentionally-close matchup (or a small `--battles` count) surfaces at least
  one `UNSTABLE` flag to prove the check actually fires, not just prints "stable" unconditionally.
