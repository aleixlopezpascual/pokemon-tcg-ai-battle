# PIMC-Oracle Blunder Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline diagnostic that plays the unmodified Archaludon base heuristic and, at
every MAIN decision, PIMC-scores its actual chosen move against its best alternative — producing a
ranked worklist of high-value-gap decisions in lost games. Root-cause and fix the top offenders in a
fresh fork of the real fallback, and gate the fixes on `src/ladder_eval.py`'s full frozen panel.

**Architecture:** Reuse the already-built, already-tested PIMC machinery in
`submissions/archaludon_intent/main.py` (`rank_options`, `_pimc_score_lines`,
`_search_begin_determinized`, `_hidden_info_kwargs`, `_rollout_to_terminal`,
`_generic_choose_options`) as a read-only oracle, imported by a new harness
`src/blunder_finder.py` modeled on `src/search_telemetry.py`'s worker/pool structure. The harness
plays real games entirely with the base heuristic's own `choose_options`/`agent`-equivalent logic
(no live override), and separately asks the PIMC oracle to value the chosen move vs. its
alternatives, writing one JSONL record per MAIN decision. A triage pass sorts/dedupes/reads the
top offenders; fixes land in a new lean fork `submissions/archaludon_lossfix/` (copied from the
real shipped fallback, not from `archaludon_intent`), each pinned by a fixture-driven unit test.

**Tech Stack:** Python 3 stdlib only (`argparse`, `json`, `multiprocessing.Pool`, `importlib`,
`pathlib`, `statistics`), the compiled `cg` engine (`cg.api`, `cg.game`), no third-party
dependencies (this whole repo's sandbox has none — see `CLAUDE.md`).

## Global Constraints

- Deadline for the Simulation ladder: **2026-08-16**.
- Sandbox has stdlib + compiled `cg` engine only — no numpy/pandas/scikit-learn (`CLAUDE.md`).
- Any code that will ship inside `submissions/archaludon_lossfix/main.py` must guard `__file__`
  lookups: try the real Kaggle sandbox path (`/kaggle_simulations/agent/deck.csv`) first, then a
  `__file__`-based fallback inside `try/except NameError` (`CLAUDE.md`'s `exec()` gotcha). The
  diagnostic harness (`src/blunder_finder.py`) is dev-only and never ships, so this constraint
  applies only to `submissions/archaludon_lossfix/main.py`.
- `submissions/**` and `data/processed/**` are gitignored per-worktree — never `git add -f` a
  submission directory or processed-data artifact.
- No seed control: `libcg.so` self-seeds from `std::random_device`. Common Random Numbers is
  impossible; sample size is the only variance-reduction lever besides the existing paired
  determinizations.
- Multiprocessing workers must be separate **processes**, never threads — the engine is a ctypes
  singleton with a process-global `Battle.battle_ptr` (see `src/search_telemetry.py`'s
  `_worker_init`/`Pool` pattern, which this plan reuses verbatim).
- Set `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS`/`MKL_NUM_THREADS`/`VECLIB_MAXIMUM_THREADS`/
  `NUMEXPR_NUM_THREADS` to `1` at module import time, before any numpy-pulling import — copy
  `src/search_telemetry.py:31-34`'s pattern verbatim into the new harness.
- Differences under **~25 μ** on `src/ladder_eval.py` are noise (empirically: two independent
  24,000-game runs of the same candidate moved ~12 μ against σ≈20). No fix is credited below that
  threshold.
- The current best committed full-panel number to beat is **676.3 μ** (n=24000,
  `masamikobayashi_archaludon_cinderace`, per the prior plan's reference table).
- Tests in this repo are plain scripts run directly (`python3 src/test_<name>.py`), no pytest
  framework — follow `src/test_search_layer.py`'s `check`/`skip`/`FAILURES`/`SKIPPED` pattern.
- Cost (games played, CPU time) is explicitly not a constraint for this project per the user's
  direction — default to generous game counts and the higher-resolution PIMC profile ("ship":
  `SEARCH_TIME_BUDGET = 10.0`, `PIMC_DETERMINIZATIONS = 40`), not the cheap "fast" profile
  (`PTCG_SEARCH_PROFILE=fast`: 3.0s / 12 draws) that `src/search_telemetry.py` uses for its own
  quick smoke runs.

---

## Reference: exact interfaces this plan consumes

All of the following already exist, unmodified, in `submissions/archaludon_intent/main.py` — this
plan reuses them by import, it does not redefine them:

- `read_deck_csv() -> list[int]` (line 136) — returns the candidate's 60-card deck ID list, with
  the Kaggle-sandbox-path guard already applied.
- `_update_opp_attack_tracking(obs)` (line 121) — mutates module globals `_opp_last_attack_id`,
  `_cur_turn_logs`; must be called once per real decision, exactly as `agent()` does, or
  `score_option`'s attack-tracking-dependent sub-scorers see stale state.
- `score_option(obs, opt) -> (score: int, reason: str)` (line 855) — the base heuristic's per-option
  scorer. Never called directly by this plan's new code; always reached through `rank_options`.
- `rank_options(obs) -> list[(score, index, reason)]` (line 1177), sorted best-first via
  `scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)`. Exceptions from `score_option` are
  caught per-option and scored `-999999`.
- `choose_options(obs) -> list[int]` (line 1196) — applies `obs.select.minCount`/`maxCount`
  selection on top of `rank_options`'s ordering. This is the real fallback's actual move-picking
  function; its output on a `maxCount == 1` MAIN decision is "the move the shipped agent makes".
- `agent(obs_dict) -> list[int]` (line 1319) — the full real entrypoint: resets
  `_opp_last_attack_id`/`_cur_turn_glogs`/`_game_search_seconds`/`_committed` on `obs.select is
  None` (start of game) and returns `read_deck_csv()`; otherwise calls
  `_update_opp_attack_tracking(obs)`, returns `[]` on no options, else
  `search_reorder(obs, choose_options(obs))` wrapped in `try/except Exception` falling back to
  `random.sample`. **This plan's harness must NOT call `agent()` directly** — `agent()` invokes
  `search_reorder`, which is the live-override search layer this plan is explicitly not
  re-running. Task 1 below builds a thin substitute that keeps `agent()`'s bookkeeping and
  fallback discipline but skips `search_reorder`.
- `_hidden_info_kwargs(obs, my_deck) -> dict` (line 1566) — samples one opponent-hidden-info draw
  (deck/hand/prize/active guess), archetype-aware via `_classify_opponent_archetype`.
- `_search_begin_determinized(obs, my_deck, kwargs=None) -> SearchState` (line 1632) — wraps
  `search_begin(obs, manual_coin=True, **(kwargs or _hidden_info_kwargs(obs, my_deck)))`.
- `_pimc_score_lines(obs, my_deck, my_index, lines, deadline) -> {key: (mean_value, draws_scored)}`
  (line 1867). `lines` is `list[(key, first_option)]` where `key` is any hashable (this plan uses
  the option's own index as `key`) and `first_option` is the option index passed to `search_step`.
  For each of up to `PIMC_DETERMINIZATIONS` shared draws (round-robin across lines, so a deadline
  cutoff leaves every line with `d` or `d-1` completed draws, never a lopsided split), it opens
  `_search_begin_determinized`, steps `first_option`, rolls out to a terminal state via
  `_rollout_to_terminal` (base policy for our own plies, `_generic_choose_options` for the
  opponent's unless the confirmed opponent archetype is our own mirror), and accumulates
  `+1`/`-1`/`0` per completed draw. Returns only keys with `draws_scored > 0`. All `search_id`s are
  released internally (`search_release`) in a `finally` block — callers never manage them.
  Deadline should be `time.time() + mod.SEARCH_TIME_BUDGET` per decision, matching the same
  per-decision cost model `search_reorder` itself uses.
- `SEARCH_PROFILE`, `SEARCH_TIME_BUDGET`, `PIMC_DETERMINIZATIONS` (lines 1399-1406) — set from
  `PTCG_SEARCH_PROFILE` env var (`"fast"` → 3.0s/12 draws, anything else including unset →
  "ship" → 10.0s/40 draws). Must be set **before** importing the candidate module (same ordering
  bug class documented in the prior plan's diagnostic script).
- `SelectContext.MAIN`, `OptionType` — imported from `cg.api` at the top of
  `archaludon_intent/main.py`; this plan's harness imports them the same way for the MAIN-decision
  guard, matching `search_reorder`'s own guard (`obs.select.context != SelectContext.MAIN`,
  `obs.select.maxCount != 1`).
- `to_observation_class(obs_dict)` — converts the raw dict `obs_dict` (as passed to `agent()`) into
  the typed `Observation` the rest of the module's functions consume. `rank_options`/
  `_pimc_score_lines` all take the typed `Observation`, not the raw dict.

Template files this plan follows structurally:
- `src/search_telemetry.py` — full worker/pool/CLI structure for the new harness (Task 1).
- `src/test_search_layer.py` — `_load_candidate`/`load_fixture`/`check`/`skip` pattern for the new
  test file (Task 4).
- `.claude/skills/run-battle/scripts/run_battle.py` — `load_deck(agent_dir: Path) -> list[int]`,
  `find_engine_dir(*candidates: Path) -> Path` helpers, both already used by
  `src/search_telemetry.py` via `_load_run_battle_module()`.

---

## Task 1: `src/blunder_finder.py` harness

**Files:**
- Create: `src/blunder_finder.py`
- Test: manual smoke run (this task has no automated test file; Task 1's own Step 5 is the test)

**Interfaces:**
- Consumes: `submissions/archaludon_intent/main.py`'s `read_deck_csv`, `_update_opp_attack_tracking`,
  `choose_options`, `rank_options`, `_pimc_score_lines`, `SEARCH_TIME_BUDGET`,
  `to_observation_class`, `SelectContext.MAIN` (all documented above); `run_battle.py`'s
  `load_deck`, `find_engine_dir`; `cg.game`'s `battle_start`, `battle_select`, `battle_finish`.
- Produces: a JSONL file, one record per MAIN decision seen during harvesting, of the exact shape:
  `{"game_id": int, "turn": int|null, "chosen_option": int, "chosen_value": float|null,
  "best_alt_option": int|null, "best_alt_value": float|null, "gap": float|null,
  "game_result": "win"|"loss"|"draw"|null}`. `game_result` is `null` until Task 1 Step 4 backfills
  it once the game concludes. Later tasks (triage, Task 2's harvest runs) consume this file's
  records by reading them as JSON lines.

- [ ] **Step 1: Write `src/blunder_finder.py`'s module header, thread-pinning, and imports**

```python
"""PIMC-oracle blunder finder for the Archaludon base heuristic.

Plays the UNMODIFIED base heuristic (no live search override) and, at every MAIN decision,
PIMC-scores the heuristic's actual chosen move against its best-ranked alternative using the
same oracle machinery built for the (now-parked) search layer in
submissions/archaludon_intent/main.py. Writes one JSONL record per decision:
{game_id, turn, chosen_option, chosen_value, best_alt_option, best_alt_value, gap, game_result}.
A large gap in a game the candidate went on to lose is a candidate blunder -- see
docs/superpowers/specs/2026-08-11-pimc-blunder-finder-design.md for the full design.

Run:
    python3 src/blunder_finder.py \\
        --candidate submissions/masamikobayashi_archaludon_cinderace \\
        --opponent submissions/soutasakurai_libraryout_crustle \\
        --games 500 --workers 8 \\
        --out data/processed/instrumentation/blunders_crustle.jsonl

Smoke-test first (few games, one worker, fast profile):
    python3 src/blunder_finder.py --candidate ... --opponent ... --games 3 --workers 1 \\
        --profile fast --out data/processed/instrumentation/blunders_smoke.jsonl
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

# Same reason as src/ladder_eval.py:66-68 and src/search_telemetry.py:31-34 -- must precede any
# numpy import in a worker.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_BATTLE_SCRIPT = REPO_ROOT / ".claude" / "skills" / "run-battle" / "scripts" / "run_battle.py"
ORACLE_DIR = REPO_ROOT / "submissions" / "archaludon_intent"

_STATE = {}
```

Note: `ORACLE_DIR` is fixed to `archaludon_intent` regardless of `--candidate` — the oracle (PIMC
scoring machinery) is always loaded from there, while `--candidate` (the agent whose real moves get
played and diagnosed) can be any submission whose base heuristic shares `score_option`'s shape
(initially `masamikobayashi_archaludon_cinderace`, the real shipped fallback).

- [ ] **Step 2: Write the module-loading and worker-init helpers**

```python
def _load_run_battle_module():
    spec = importlib.util.spec_from_file_location("run_battle_mod", RUN_BATTLE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_module(main_py, module_name):
    sys.path.insert(0, str(Path(main_py).parent))
    spec = importlib.util.spec_from_file_location(module_name, main_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _worker_init(engine_dir, cand_dir, opp_dir, profile):
    """Import the candidate, the oracle, and the opponent once per process.

    The oracle module (`archaludon_intent/main.py`) is imported separately from the candidate so
    that PIMC scoring machinery is available even when `--candidate` is a lean fork (like
    `archaludon_lossfix`) that never had the search layer's Tasks 5-10 code appended to it. Only
    the oracle needs `PTCG_SEARCH_PROFILE` set before import -- the candidate and opponent don't
    read that env var.
    """
    os.environ["PTCG_SEARCH_PROFILE"] = profile
    sys.path.insert(0, str(engine_dir))
    from cg.game import battle_start, battle_finish, battle_select  # noqa: F401
    rb = _load_run_battle_module()
    _STATE["rb"] = rb
    _STATE["battle_start"] = battle_start
    _STATE["battle_select"] = battle_select
    _STATE["battle_finish"] = battle_finish
    _STATE["cand_mod"] = _import_module(Path(cand_dir) / "main.py", "cand_main")
    _STATE["oracle_mod"] = _import_module(ORACLE_DIR / "main.py", "oracle_main")
    _STATE["opp_mod"] = _import_module(Path(opp_dir) / "main.py", "opp_main")
    _STATE["cand_deck"] = rb.load_deck(Path(cand_dir))
    _STATE["opp_deck"] = rb.load_deck(Path(opp_dir))
```

- [ ] **Step 3: Write the base-heuristic move driver (`agent()`-equivalent minus search_reorder)**

This replicates `archaludon_intent.main.agent()`'s exact bookkeeping and fail-closed fallback
(lines 1319-1337 of that file), but calls the **candidate's own** `choose_options` instead of the
oracle's `search_reorder(obs, choose_options(obs))` — the whole point of this harness is that the
real move is never search-overridden:

```python
def _base_agent_move(cand, obs_dict):
    """`archaludon_intent.agent()`'s bookkeeping and fallback, without the search_reorder call."""
    obs = cand.to_observation_class(obs_dict)
    if obs.select is None:
        cand._opp_last_attack_id = None
        cand._cur_turn_logs.clear()
        return cand.read_deck_csv()
    cand._update_opp_attack_tracking(obs)
    if not obs.select.option:
        return []
    try:
        return cand.choose_options(obs)
    except Exception:
        import random
        n_options = len(obs.select.option)
        k = max(obs.select.minCount, min(obs.select.maxCount, n_options))
        return random.sample(list(range(n_options)), k) if k > 0 else []
```

- [ ] **Step 4: Write the diagnostic scorer, per-game player, and chunk runner**

```python
def _diagnose_decision(oracle, cand_deck, obs_dict, chosen, k=4):
    """PIMC-score `chosen`'s first move against its top-(k-1) ranked alternatives.

    Returns a dict matching the JSONL record shape (minus game_id/game_result, filled by the
    caller), or None if this wasn't a scoreable single-select MAIN decision. Never raises -- any
    internal error is caught and reported as a record with best_alt_value=None, matching the
    design's fail-closed discipline (this is read-only instrumentation, it must never affect the
    real game already decided by `chosen`).
    """
    obs = oracle.to_observation_class(obs_dict)
    if obs.select is None or obs.select.context != oracle.SelectContext.MAIN:
        return None
    if obs.select.maxCount != 1 or not chosen:
        return None
    chosen_option = chosen[0]
    try:
        ranked = oracle.rank_options(obs)  # [(score, index, reason), ...] best-first
        alt_indices = [i for _, i, _ in ranked if i != chosen_option][:k - 1]
        lines = [(chosen_option, chosen_option)] + [(i, i) for i in alt_indices]
        my_index = obs.current.yourIndex
        deadline = time.time() + oracle.SEARCH_TIME_BUDGET
        values = oracle._pimc_score_lines(obs, cand_deck, my_index, lines, deadline)
    except Exception:
        return {
            "turn": getattr(obs.current, "turn", None),
            "chosen_option": chosen_option,
            "chosen_value": None, "best_alt_option": None, "best_alt_value": None, "gap": None,
        }
    chosen_value = values.get(chosen_option, (None, 0))[0]
    alt_values = {i: v[0] for i, v in values.items() if i != chosen_option}
    best_alt_option = max(alt_values, key=alt_values.get) if alt_values else None
    best_alt_value = alt_values.get(best_alt_option) if best_alt_option is not None else None
    gap = (best_alt_value - chosen_value
           if chosen_value is not None and best_alt_value is not None else None)
    return {
        "turn": getattr(obs.current, "turn", None),
        "chosen_option": chosen_option,
        "chosen_value": chosen_value,
        "best_alt_option": best_alt_option,
        "best_alt_value": best_alt_value,
        "gap": gap,
    }


def _play_one(cand, oracle, opp, cand_deck, cand_first, game_id, records):
    bs, bsel, bfin = _STATE["battle_start"], _STATE["battle_select"], _STATE["battle_finish"]
    cd, od = _STATE["cand_deck"], _STATE["opp_deck"]
    decks = (cd, od) if cand_first else (od, cd)
    obs, start_data = bs(decks[0], decks[1])
    if obs is None:
        print(f"battle start failed: errorPlayer={start_data.errorPlayer} "
              f"errorType={start_data.errorType}", file=sys.stderr)
        return
    cand_index = 0 if cand_first else 1
    game_records = []
    try:
        while obs["current"]["result"] == -1:
            actor = obs["current"]["yourIndex"]
            if actor == cand_index:
                chosen = _base_agent_move(cand, obs)
                diag = _diagnose_decision(oracle, cand_deck, obs, chosen)
                if diag is not None:
                    diag["game_id"] = game_id
                    game_records.append(diag)
                move = chosen
            else:
                move = opp.agent(obs)
            obs = bsel(move)
        winner = obs["current"]["result"]
    finally:
        bfin()
    result = "draw" if winner == -2 else ("win" if winner == cand_index else "loss")
    for rec in game_records:
        rec["game_result"] = result
    records.extend(game_records)


def _play_chunk(task):
    n, offset = task
    cand, oracle, opp = _STATE["cand_mod"], _STATE["oracle_mod"], _STATE["opp_mod"]
    cand_deck = _STATE["cand_deck"]
    records = []
    t0 = time.time()
    for i in range(n):
        _play_one(cand, oracle, opp, cand_deck, (offset + i) % 2 == 0, offset + i, records)
    return records, time.time() - t0
```

`winner == -2` for a draw follows the same result-code convention `src/local_eval.py` and
`src/ladder_eval.py` already use for this engine (`game-engine-analyst` confirms `Battle.result`
is `-1` in-progress, `0`/`1` a player index win, `-2` a draw) — do not invent a different sentinel.

- [ ] **Step 5: Write the CLI entrypoint**

```python
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--games", type=int, default=500)
    ap.add_argument("--workers", type=int,
                    default=max(1, min(8, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--profile", choices=["fast", "ship"], default="ship",
                    help="PIMC resolution: ship=40 draws/10s (default, cost is not a constraint "
                         "for this project), fast=12 draws/3s (for quick smoke runs only)")
    ap.add_argument("--out", required=True, help="write JSONL records here")
    args = ap.parse_args()

    cand = Path(args.candidate).resolve()
    opp = Path(args.opponent).resolve()
    rb = _load_run_battle_module()
    engine_dir = rb.find_engine_dir(
        cand, opp, REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission")

    workers = args.workers
    per = max(1, args.games // workers)
    tasks = [(per, i * per) for i in range(workers)]
    init = (str(engine_dir), str(cand), str(opp), args.profile)

    if workers == 1:
        _worker_init(*init)
        results = [_play_chunk(t) for t in tasks]
    else:
        with Pool(workers, initializer=_worker_init, initargs=init) as pool:
            results = list(pool.imap_unordered(_play_chunk, tasks))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total_records = 0
    total_seconds = sum(r[1] for r in results)
    with out.open("w") as f:
        for records, _ in results:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
                total_records += 1
    games = sum(t[0] for t in tasks)
    print(f"games={games} decisions={total_records} cpu_seconds={total_seconds:.1f} -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Smoke-test the harness**

Run:
```bash
python3 src/blunder_finder.py \
    --candidate submissions/masamikobayashi_archaludon_cinderace \
    --opponent submissions/soutasakurai_libraryout_crustle \
    --games 3 --workers 1 --profile fast \
    --out data/processed/instrumentation/blunders_smoke.jsonl
```
Expected: no traceback, printed summary line (`games=3 decisions=N ...`), and
`data/processed/instrumentation/blunders_smoke.jsonl` is non-empty with every line valid JSON
containing `game_result` in `{"win", "loss", "draw"}` (never `null` — Step 4's backfill runs
unconditionally at game end) and `chosen_option` an `int`. Spot-check a few records: `gap` should
be `>= 0` whenever both `chosen_value` and `best_alt_value` are non-null, since `best_alt_option`
is chosen by `max(...)` over alternatives only — a chosen option can still beat every alternative
sampled, giving `gap` computed from a `best_alt_value` below `chosen_value` (a **negative** gap is
valid and simply means the base heuristic's own pick already looked best of the sampled set; do
not treat this as a bug).

- [ ] **Step 7: Commit**

```bash
git add src/blunder_finder.py
git commit -m "feat: add PIMC-oracle blunder finder harness"
```

---

## Task 2: Harvest runs vs. the two worst matchups

**Files:**
- Create (gitignored, not committed): `data/processed/instrumentation/blunders_crustle.jsonl`,
  `data/processed/instrumentation/blunders_alakazam.jsonl`

**Interfaces:**
- Consumes: `src/blunder_finder.py`'s CLI from Task 1.
- Produces: two JSONL files consumed by Task 3's triage script.

- [ ] **Step 1: Harvest vs. Crustle (worst matchup, 33.5%)**

```bash
python3 src/blunder_finder.py \
    --candidate submissions/masamikobayashi_archaludon_cinderace \
    --opponent submissions/soutasakurai_libraryout_crustle \
    --games 600 --workers 8 --profile ship \
    --out data/processed/instrumentation/blunders_crustle.jsonl
```
Expected: completes without traceback; prints `games=600 decisions=N ...` with `N` on the order of
several thousand (roughly 25-50 MAIN decisions/game per the prior plan's telemetry, times 600
games, times ~1 candidate-side game in 2 since `cand_first` alternates but every game still has a
candidate side). Do not proceed to Step 2 if this errors — fix the harness first (back to Task 1).

- [ ] **Step 2: Harvest vs. Alakazam/Dunsparce (second-worst matchup, 42.1%)**

```bash
python3 src/blunder_finder.py \
    --candidate submissions/masamikobayashi_archaludon_cinderace \
    --opponent submissions/biohack44_alakazam_dunsparce \
    --games 600 --workers 8 --profile ship \
    --out data/processed/instrumentation/blunders_alakazam.jsonl
```

- [ ] **Step 3: Check the loss-decision yield; scale up if thin**

```bash
python3 -c "
import json
for name in ('blunders_crustle', 'blunders_alakazam'):
    path = f'data/processed/instrumentation/{name}.jsonl'
    recs = [json.loads(l) for l in open(path)]
    losses = [r for r in recs if r['game_result'] == 'loss' and r.get('gap') is not None]
    high_gap = [r for r in losses if r['gap'] > 0.3]
    print(name, 'total', len(recs), 'loss-decisions', len(losses), 'gap>0.3', len(high_gap))
"
```
If `gap>0.3` is under ~20 for either matchup, re-run that matchup's Step with `--games 1500`
(append via a second `--out` file and concatenate, or simply overwrite with a larger `--games`) —
cost is not a constraint per this project's standing direction. Do not proceed to Task 3 with a
worklist so thin that dedup (Task 3) would collapse it to fewer than ~5 distinct situations.

- [ ] **Step 4: No commit** (these files are gitignored instrumentation data, matching
`data/processed/**`'s existing gitignore status — do not attempt to `git add -f` them).

---

## Task 3: Triage script and worklist

**Files:**
- Create: `src/triage_blunders.py`
- Create (gitignored): `data/processed/instrumentation/blunder_worklist.json`

**Interfaces:**
- Consumes: the two JSONL files from Task 2, each record shaped
  `{game_id, turn, chosen_option, chosen_value, best_alt_option, best_alt_value, gap,
  game_result}`.
- Produces: `blunder_worklist.json`, a JSON list of dicts
  `{"matchup": str, "gap": float, "turn": int|null, "count": int, "example_game_ids": [int, ...]}`
  sorted by `gap` descending, deduplicated by `(matchup, turn)` bucket (see Step 2) — this is what
  a human (or `game-engine-analyst`) reads to pick the next root-cause target in Task 4.

- [ ] **Step 1: Write the loader and filter**

```python
"""Sort/dedupe PIMC-oracle blunder records into a root-cause worklist.

Run:
    python3 src/triage_blunders.py \\
        data/processed/instrumentation/blunders_crustle.jsonl:crustle \\
        data/processed/instrumentation/blunders_alakazam.jsonl:alakazam \\
        --out data/processed/instrumentation/blunder_worklist.json
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_losses(path):
    """Loss-game records with a computed gap, the only ones triage cares about."""
    recs = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return [r for r in recs if r["game_result"] == "loss" and r.get("gap") is not None]
```

- [ ] **Step 2: Write the dedup/bucket logic**

Two occurrences of "the same bug" recur at similar turn numbers within one matchup (per the
design's "same `turn`-range archetype pattern" dedup rule) — bucket by `(matchup, turn // 2)` (a
2-turn window absorbs off-by-one turn counting between the two players' turn numbering) and keep
the max-gap example plus a running count per bucket:

```python
def bucket_key(turn):
    return turn // 2 if turn is not None else "unknown"


def build_worklist(sources):
    """`sources` is [(path, matchup_label), ...]. Returns the sorted, deduped worklist."""
    buckets = defaultdict(lambda: {"gap": float("-inf"), "count": 0, "example_game_ids": []})
    for path, matchup in sources:
        for rec in load_losses(path):
            key = (matchup, bucket_key(rec["turn"]))
            b = buckets[key]
            b["count"] += 1
            if len(b["example_game_ids"]) < 3:
                b["example_game_ids"].append(rec["game_id"])
            if rec["gap"] > b["gap"]:
                b["gap"] = rec["gap"]
                b["turn"] = rec["turn"]
                b["chosen_option"] = rec["chosen_option"]
                b["best_alt_option"] = rec["best_alt_option"]

    worklist = []
    for (matchup, _), b in buckets.items():
        worklist.append({
            "matchup": matchup,
            "gap": b["gap"],
            "turn": b.get("turn"),
            "count": b["count"],
            "example_game_ids": b["example_game_ids"],
            "chosen_option": b.get("chosen_option"),
            "best_alt_option": b.get("best_alt_option"),
        })
    worklist.sort(key=lambda w: w["gap"], reverse=True)
    return worklist
```

- [ ] **Step 3: Write the CLI**

```python
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+", help="path:matchup_label pairs")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    sources = []
    for s in args.sources:
        path, _, label = s.partition(":")
        sources.append((path, label or Path(path).stem))
    worklist = build_worklist(sources)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(worklist, indent=2))
    print(f"{len(worklist)} distinct decision buckets -> {args.out}")
    for w in worklist[:10]:
        print(f"  gap={w['gap']:.3f} matchup={w['matchup']} turn={w['turn']} "
              f"count={w['count']} chosen={w['chosen_option']} alt={w['best_alt_option']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it against Task 2's harvest**

```bash
python3 src/triage_blunders.py \
    data/processed/instrumentation/blunders_crustle.jsonl:crustle \
    data/processed/instrumentation/blunders_alakazam.jsonl:alakazam \
    --out data/processed/instrumentation/blunder_worklist.json
```
Expected: no traceback, prints at least a few distinct buckets with the top-10 summary. If the
list is empty, go back to Task 2 Step 3's scale-up guidance rather than proceeding — an empty
worklist means the fallback-to-manual-reading contingency (Task 6) should trigger, not that this
task is "done".

- [ ] **Step 5: Commit the script (not the data)**

```bash
git add src/triage_blunders.py
git commit -m "feat: add triage script for PIMC-oracle blunder worklist"
```

---

## Task 4: Root-cause and fix the top offenders in `archaludon_lossfix`

**Files:**
- Create (gitignored, not committed): `submissions/archaludon_lossfix/` (copied from
  `submissions/masamikobayashi_archaludon_cinderace/`)
- Create: `src/test_lossfix.py`
- Modify: `submissions/archaludon_lossfix/main.py` (one or more fixes, per sub-steps below)

**Interfaces:**
- Consumes: `blunder_worklist.json` from Task 3; the captured `obs` state for a specific
  `game_id`/`turn` (re-derivable via a targeted `--dump-main-states`-style capture, see Step 1);
  `submissions/masamikobayashi_archaludon_cinderace/main.py`'s `score_option` and its sub-scorers
  (the fix target).
- Produces: `submissions/archaludon_lossfix/main.py`, a fork of the real fallback with the
  fixes applied, consumed by Task 5's gate.

This task's exact fix content cannot be pre-specified — it depends on what Task 3's worklist
surfaces, which does not exist yet. What follows is the fixed process every offender goes through,
plus the one-time fork setup.

- [ ] **Step 1: Fork the real fallback**

```bash
cp -r submissions/masamikobayashi_archaludon_cinderace submissions/archaludon_lossfix
```
Verify the fork is untouched and importable:
```bash
python3 -c "
import sys, importlib.util
sys.path.insert(0, 'data/raw/sample_submission/sample_submission')
sys.path.insert(0, 'submissions/archaludon_lossfix')
spec = importlib.util.spec_from_file_location('m', 'submissions/archaludon_lossfix/main.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('deck size', len(m.read_deck_csv()))
"
```
Expected: prints `deck size 60`, no traceback.

- [ ] **Step 2: Write `src/test_lossfix.py`'s skeleton (fixture-driven, skips cleanly)**

```python
"""Tests pinning submissions/archaludon_lossfix/main.py's base-heuristic fixes.

Run: python3 src/test_lossfix.py

Each fix gets a captured-obs fixture (a single MAIN-decision obs_dict, saved as JSON under
data/processed/instrumentation/lossfix_fixtures/<name>.json) and a before/after assertion on
score_option's or a named sub-scorer's return value. Skips cleanly when the candidate or a
fixture is absent (both are gitignored)."""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FAILURES = []
SKIPPED = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}   {detail}")
        FAILURES.append(name)


def skip(name, why):
    print(f"  skip  {name}   ({why})")
    SKIPPED.append(name)


def _load_candidate(dirname="archaludon_lossfix"):
    agent_dir = REPO_ROOT / "submissions" / dirname
    main_py = agent_dir / "main.py"
    if not main_py.exists():
        return None
    engine_dir = REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission"
    if not (engine_dir / "cg").is_dir():
        return None
    for p in (str(engine_dir), str(agent_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("lossfix_under_test", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lossfix_under_test"] = module
    spec.loader.exec_module(module)
    return module


def load_fixture(name):
    path = REPO_ROOT / "data" / "processed" / "instrumentation" / "lossfix_fixtures" / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def main():
    m = _load_candidate()
    if m is None:
        skip("all lossfix tests", "submissions/archaludon_lossfix not present locally")
    else:
        run_all_tests(m)
    print(f"\n{len(FAILURES)} failed, {len(SKIPPED)} skipped")
    if FAILURES:
        sys.exit(1)


def run_all_tests(m):
    pass  # each fix sub-step below appends one test_<fix_name>(m) call here


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it once to confirm the skeleton skips cleanly**

Run: `python3 src/test_lossfix.py`
Expected: `skip  all lossfix tests   (submissions/archaludon_lossfix not present locally)` only if
run in an environment without the fork; since Step 1 just created it locally, expect instead
`0 failed, 0 skipped` (no tests registered yet — `run_all_tests` is still empty).

- [ ] **Step 4: Commit the harness/skeleton before starting root-cause work**

```bash
git add src/test_lossfix.py
git commit -m "test: add fixture-driven test skeleton for archaludon_lossfix fixes"
```

- [ ] **Step 5: For the #1 worklist entry, capture its exact decision context**

Read `blunder_worklist.json`'s top entry: note `matchup`, `turn`, `example_game_ids`,
`chosen_option`, `best_alt_option`. Capture the real `obs_dict` at that turn by re-running a small
`--dump-main-states`-style harvest against the same matchup and filtering to the matching turn
(reuse `src/search_telemetry.py --dump-main-states`, pointed at
`submissions/masamikobayashi_archaludon_cinderace` vs. the matchup's opponent, then grep the
dumped JSONL for `"turn": <N>` records) — save the first matching record to
`data/processed/instrumentation/lossfix_fixtures/<matchup>_turn<N>.json`.

- [ ] **Step 6: Root-cause the decision**

Dispatch the `game-engine-analyst` agent (or read directly) with: the captured `obs_dict`, the
`chosen_option` and `best_alt_option` indices, and `submissions/masamikobayashi_archaludon_cinderace/
main.py`'s `score_option` (line 855) plus whichever sub-scorer function produced the chosen
option's score (trace via the option's `type`/`context` fields against `score_option`'s dispatch).
The question to answer: **why did the base heuristic's `score_option` rank `chosen_option` above
`best_alt_option` here, and is that ranking a bug** (a missing case, an inverted comparison, a
magic number that doesn't generalize past the archetype it was tuned on — the same defect shapes
as the `random.sample` clip fix and the `detect_matchup` None-guard fix) **or a correct call the
PIMC oracle's rollout just modeled pessimistically** (e.g., the generic opponent stand-in
undervaluing a real defensive line)? Only proceed to Step 7 if the answer is a concrete,
nameable heuristic bug — if the oracle's own approximation is the actual cause, discard this
worklist entry and move to the next one instead of forcing a fix.

- [ ] **Step 7: Write the failing fixture test**

Exact test code depends on the concrete bug found in Step 6. Structural pattern (fill in
`<bug_name>`, `<sub_scorer_or_score_option>`, `<expected_after_fix>` once Step 6 identifies them):

```python
def test_<bug_name>(m):
    fixture = load_fixture("<matchup>_turn<N>.json")
    if fixture is None:
        skip("<bug_name>", "fixture not captured")
        return
    obs = m.to_observation_class(fixture)
    opt = obs.select.option[<chosen_option_index>]
    score, reason = m.<sub_scorer_or_score_option>(obs, opt)
    check("<bug_name> no longer over-scores the blunder option",
          score < <expected_after_fix>, f"got score={score}")
```

Add the call `test_<bug_name>(m)` inside `run_all_tests` in `src/test_lossfix.py`.

- [ ] **Step 8: Run it to confirm it fails against the unfixed fork**

Run: `python3 src/test_lossfix.py`
Expected: `FAIL  <bug_name> no longer over-scores the blunder option   got score=<current>`.

- [ ] **Step 9: Apply the minimal fix in `submissions/archaludon_lossfix/main.py`**

Edit only the specific comparison/case/constant identified in Step 6 — no unrelated refactoring
(per this repo's YAGNI convention and the design's "fresh, lean fork" intent).

- [ ] **Step 10: Run the test to confirm it passes**

Run: `python3 src/test_lossfix.py`
Expected: `ok    <bug_name> no longer over-scores the blunder option`, `0 failed`.

- [ ] **Step 11: Commit this fix**

```bash
git add submissions/archaludon_lossfix/main.py src/test_lossfix.py \
    data/processed/instrumentation/lossfix_fixtures/<matchup>_turn<N>.json 2>/dev/null
git commit -m "fix: <one-line description of the base-heuristic bug fixed>"
```
Note: `submissions/**` and `data/processed/**` are gitignored — this `git add` will silently no-op
on those paths (confirm with `git status` that only `src/test_lossfix.py` and the plan/worklist
docs, if any, actually stage). Only `src/test_lossfix.py` and this plan's own tracked files should
land in the commit; the fix to `main.py` and the fixture JSON live only on disk per this repo's
established policy of never force-adding submission directories.

- [ ] **Step 12: Repeat Steps 5-11 for the next several worklist entries**

Work down `blunder_worklist.json` in `gap`-descending order. Stop this task's iteration (move to
Task 5) once either: (a) 5 concrete fixes have been applied, or (b) the next worklist entry's root
cause (Step 6) turns out to be oracle approximation noise rather than a real heuristic bug, two
entries in a row — whichever comes first. This bound exists so Task 4 doesn't run forever chasing
diminishing-quality entries; Task 5's gate is the real arbiter of whether the fixes accumulated so
far are worth shipping.

---

## Task 5: Full frozen-panel gate

**Files:**
- No new files. Reads `submissions/archaludon_lossfix/` (Task 4's output) and
  `data/processed/panel_ratings.json` (existing, frozen).

**Interfaces:**
- Consumes: `src/ladder_eval.py`'s existing `rate` subcommand (no changes to that script).

- [ ] **Step 1: Run the full frozen-panel gate**

```bash
python3 src/ladder_eval.py rate --candidate submissions/archaludon_lossfix --games 4000 \
    --workers 8 --json data/processed/ratings/archaludon_lossfix.json
```

- [ ] **Step 2: Compare against the reference number**

Read the printed/JSON `mu` value. Compare against **676.3** (the current best committed full-panel
number, `masamikobayashi_archaludon_cinderace`, n=24000).

- If `mu - 676.3 > 25` (CLAUDE.md's noise floor): a real improvement. Proceed to Step 3.
- If `|mu - 676.3| <= 25`: parity, same outcome as every prior mechanism this project has tried.
  Do not ship. Log the result in `notebooks/kaggle-research/10-day-plan.md`'s submission-log
  section (append a dated entry: mechanism tried, μ, verdict) and proceed to Task 6 (fallback to
  manual reading) rather than iterating further on this same worklist — a `+25` bar that four
  independent PIMC/base-heuristic attempts have now failed to clear on the first pass is a signal
  to change method, not to retry the same one a fifth time blind.
- If `mu < 676.3 - 25`: a real regression. One or more of Task 4's fixes made things worse — bisect
  by reverting fixes one at a time (`git log --oneline` on `archaludon_lossfix`'s working tree
  changes, since the dir itself isn't committed, so bisection here means re-copying from the
  fallback and re-applying fixes N-1 at a time) and re-running this gate, until the regressing fix
  is isolated. Drop that one fix, keep the rest, re-gate.

- [ ] **Step 3 (only if a real improvement was measured): confirm with a second independent run**

```bash
python3 src/ladder_eval.py rate --candidate submissions/archaludon_lossfix --games 4000 \
    --workers 8 --json data/processed/ratings/archaludon_lossfix_run2.json
```
Both runs must show `mu - 676.3 > 25` before this candidate is treated as a real improvement,
per the same two-independent-24000-game-runs-can-move-12μ noise finding in CLAUDE.md — a single
4000-game run is smaller than that reference and correspondingly noisier.

- [ ] **Step 4: Log the result**

Append a dated entry to `notebooks/kaggle-research/10-day-plan.md`'s submission-log section:
mechanism (PIMC-oracle blunder finder), fixes applied (list from Task 4's commits), both gate
readings, verdict (ship / parity / regression). This is a tracked file — commit it:

```bash
git add notebooks/kaggle-research/10-day-plan.md
git commit -m "docs: log PIMC-oracle blunder-finder gate result"
```

- [ ] **Step 5 (only if shipping): prepare and submit**

Follow the same tar-validation and `py_compile` discipline every prior submission in this repo
has used (`CLAUDE.md`'s "Submission discipline" section): verify
`{"main.py", "deck.csv", "cg/api.py", "cg/libcg.so"}` are present in the tarball, `py_compile
submissions/archaludon_lossfix/main.py` cleanly, then `kaggle competitions submit`. This step is
gated on the human confirming they want to spend one of the 5 daily/2-concurrent submission slots
on this candidate — do not submit without that confirmation, per this session's standing
risky-action discipline.

---

## Task 6: Fallback to manual loss reading (contingency, only if Task 5 shows parity)

**Files:**
- No new files — uses `src/local_eval.py`'s existing `--save-losses`/`--repeats` flags.

**Interfaces:**
- Consumes: `src/local_eval.py`'s existing CLI (`--candidate`, `--opponents`, `--battles`,
  `--save-losses <dir>`, `--repeats`).

- [ ] **Step 1: Save loss replays for manual reading**

```bash
python3 src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace \
    --opponents submissions/soutasakurai_libraryout_crustle \
    --battles 200 --save-losses data/processed/instrumentation/lossfix_replays_crustle \
    --repeats 1
```
Repeat with `--opponents submissions/biohack44_alakazam_dunsparce` for the second matchup.

- [ ] **Step 2: Read a sample of saved replays by hand**

Drag the saved JSON files into the community visualizer.html referenced by `local_eval.py`'s own
`--save-losses` help text, or read the raw JSON turn-by-turn. Focus specifically on patterns a
single-decision value-gap metric cannot see: a *sequence* of individually-locally-optimal
decisions that is collectively bad (e.g., over-committing energy to a Pokemon that gets KO'd
before attacking, across several turns each of which looked fine in isolation).

- [ ] **Step 3: Feed any new findings back into Task 4's loop**

Any concrete bug found this way gets the same treatment as a worklist entry: fixture test in
`src/test_lossfix.py`, fix in `submissions/archaludon_lossfix/main.py`, re-gate via Task 5.

---

## Self-Review (performed after writing this plan, before handoff)

**1. Spec coverage** — all 6 components of
`docs/superpowers/specs/2026-08-11-pimc-blunder-finder-design.md` map to a task: harness → Task 1,
harvest runs → Task 2, triage → Task 3, fork+fixes → Task 4, full-panel gate → Task 5, fallback →
Task 6. The design's "Data flow" diagram's every stage has a corresponding step. The design's
"Error handling" fail-closed requirement is implemented in Task 1 Step 4's `_diagnose_decision`
(try/except around the PIMC call only, never around the already-decided real move). The design's
"Testing" section's three bullets map to Task 1 Step 6 (smoke test), Task 4 Steps 7-10 (fixture
tests), and Task 5 (full-panel gate as final arbiter).

**2. Placeholder scan** — Task 4's fix-specific steps (5-11) cannot contain concrete before/after
values because the bug they target is not yet known (that's the point of the harness); this is
flagged explicitly in the task's own preamble rather than silently glossed over, and every
surrounding step (fork setup, test skeleton, CLI, commit discipline) is fully concrete. No other
task contains a TBD/TODO.

**3. Type consistency** — `_diagnose_decision`'s return dict keys (`turn`, `chosen_option`,
`chosen_value`, `best_alt_option`, `best_alt_value`, `gap`) match the JSONL record shape declared
in Task 1's Interfaces block and consumed by Task 3's `load_losses`/`build_worklist`. `game_id`
and `game_result` are added by `_play_one`/`_diagnose_decision`'s caller, not by
`_diagnose_decision` itself — consistent between Task 1 Step 4's code and Step 6's smoke-test
expectations. `_pimc_score_lines`'s `lines` parameter shape (`list[(key, first_option)]`) matches
between the Reference section and Task 1 Step 4's actual call site (`lines = [(chosen_option,
chosen_option)] + [(i, i) for i in alt_indices]`, using the option index as both key and
first_option, a valid choice since `_pimc_score_lines` only requires `key` be hashable and
`first_option` be a legal option index).
