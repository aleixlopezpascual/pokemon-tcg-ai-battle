# Local Eval Harness Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close three documented gaps in `src/local_eval.py` (narrow opponent pool, no
replay/failure detail, no stability check) per
`docs/superpowers/specs/2026-08-07-local-eval-harness-improvements-design.md`.

**Architecture:** Three additive changes to the single existing file `src/local_eval.py`: extend
`DEFAULT_OPPONENTS`, add an opt-in `--save-losses` flag that dumps engine-native replay JSON on
candidate losses, and an opt-in `--repeats` flag that runs each matchup multiple independent
times and flags ranking instability. No new files, no new dependencies.

**Tech Stack:** Python 3 stdlib only (`argparse`, `json`, `math`, `pathlib`), the competition's
compiled `cg` engine (`cg.game.battle_start`/`battle_select`/`battle_finish`/`visualize_data`).

## Global Constraints

- No test framework exists in this repo (confirmed: no `test_*.py`/`*_test.py` files anywhere).
  Verification in every task below is a real command run against the actual `cg` engine and real
  submission agents, not `pytest` — this matches how `local_eval.py` and the `run-battle` skill
  are already verified elsewhere in this repo.
- Default invocation (`--candidate X`, no other flags) must produce output identical in shape to
  today's — every new flag is opt-in and changes nothing when omitted.
- This worktree has no `submissions/` or `data/raw/` (gitignored, only present in the main
  checkout at `/Users/aleix.lopez/pokemon-tcg-ai-battle`). Task 1 copies only what's needed
  (`submissions/`, 13M, and `data/raw/sample_submission/`, 5.3M) — **not** all of `data/raw/`,
  since `data/raw/episodes/` alone is 1.2GB and irrelevant to running battles.
- `submissions/` and `data/raw/` are gitignored in both the main checkout and this worktree —
  copying them does not create anything to commit.

---

### Task 1: Copy local test fixtures into this worktree

**Files:**
- Create (untracked, gitignored): `submissions/` (copied from main checkout)
- Create (untracked, gitignored): `data/raw/sample_submission/` (copied from main checkout)

**Interfaces:**
- Produces: `submissions/masamikobayashi_archaludon_cinderace/`,
  `submissions/kiyota_mega_lucario_ex/`, `submissions/soutasakurai_libraryout_crustle/`,
  `submissions/il_agent_v2b/` (all with `main.py` + `deck.csv`), and
  `data/raw/sample_submission/sample_submission/` (contains the `cg/` engine package used by
  every later task).

- [ ] **Step 1: Copy `submissions/`**

```bash
cp -R /Users/aleix.lopez/pokemon-tcg-ai-battle/submissions /Users/aleix.lopez/pokemon-tcg-ai-battle/.claude/worktrees/dynamic-honking-rocket/submissions
```

- [ ] **Step 2: Copy `data/raw/sample_submission/`**

```bash
mkdir -p /Users/aleix.lopez/pokemon-tcg-ai-battle/.claude/worktrees/dynamic-honking-rocket/data/raw
cp -R /Users/aleix.lopez/pokemon-tcg-ai-battle/data/raw/sample_submission /Users/aleix.lopez/pokemon-tcg-ai-battle/.claude/worktrees/dynamic-honking-rocket/data/raw/sample_submission
```

- [ ] **Step 3: Verify the existing harness runs unmodified**

Run: `python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 4`
Expected: prints a 4-row table (opponent/wins/games/errors/win%/95% CI) against the *current*
`DEFAULT_OPPONENTS` (random baseline + kiyota + masamikobayashi + soutasakurai — this candidate
is filtered out of its own opponent list), plus a pooled line. No tracebacks.

No commit — these directories are gitignored (`git status --short` should show no changes from
this task).

---

### Task 2: Add `il_agent_v2b` to the default opponent roster

**Files:**
- Modify: `src/local_eval.py:24-29` (the `DEFAULT_OPPONENTS` list)

**Interfaces:**
- Consumes: `submissions/il_agent_v2b/main.py` + `deck.csv` (from Task 1).
- Produces: `DEFAULT_OPPONENTS` now has 5 entries; every later task's default-roster runs pick
  this up automatically since nothing else references the list by length.

- [ ] **Step 1: Edit `DEFAULT_OPPONENTS`**

In `src/local_eval.py`, change:

```python
DEFAULT_OPPONENTS = [
    REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission",
    REPO_ROOT / "submissions" / "kiyota_mega_lucario_ex",
    REPO_ROOT / "submissions" / "masamikobayashi_archaludon_cinderace",
    REPO_ROOT / "submissions" / "soutasakurai_libraryout_crustle",
]
```

to:

```python
DEFAULT_OPPONENTS = [
    REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission",
    REPO_ROOT / "submissions" / "kiyota_mega_lucario_ex",
    REPO_ROOT / "submissions" / "masamikobayashi_archaludon_cinderace",
    REPO_ROOT / "submissions" / "soutasakurai_libraryout_crustle",
    REPO_ROOT / "submissions" / "il_agent_v2b",
]
```

(`il_agent_v1` and `il_agent_v2` are deliberately excluded — v1 has a confirmed bug always
returning `maxCount` options and ships a deck that barely appears in its own training data; v2
is superseded by v2b's identical policy with a dependency-free model export, so including both
would just duplicate one opponent's behavior rather than add diversity.)

- [ ] **Step 2: Verify the roster grew and the new opponent runs**

Run: `python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 4`
Expected: now a **5-row** table, including a row named `il_agent_v2b` with a non-error win rate
(some wins/losses, not 4/4 errors — a 4/4 errors row would mean `il_agent_v2b/main.py` failed to
load or crashed every game, which would mean this task isn't done).

- [ ] **Step 3: Commit**

```bash
git add src/local_eval.py
git commit -m "$(cat <<'EOF'
Add il_agent_v2b to local_eval.py's default opponent roster

Widens the pool from 4 same-tier rule-based agents to include a
trained (imitation-learning) opponent on a different archetype,
per evaluation-methodology.md's community precedent for why a
narrow local pool inverts rankings the real ladder gets right.
EOF
)"
```

---

### Task 3: `--save-losses DIR` replay capture

**Files:**
- Modify: `src/local_eval.py` — add `import json` at the top; modify `run_matchup` (currently
  `src/local_eval.py:50-82`) to accept and use a new `save_losses_dir` parameter; modify `main()`
  (currently `src/local_eval.py:85-121`) to add the CLI flag and pass it through.

**Interfaces:**
- Consumes: `cg.game.visualize_data` (new import inside `run_matchup`, alongside the existing
  `battle_start`/`battle_select`/`battle_finish` import) — confirmed API from
  `notebooks/kaggle-research/pulled/kiyotah__how-to-output-local-battle-as-json-and-view/how-to-output-local-battle-as-json-and-view.ipynb`.
- Produces: `run_matchup(rb, candidate_dir, opponent_dir, battles, engine_dir, save_losses_dir=None)`
  — the new 6th parameter is keyword-friendly with a default, so Task 4's repeat-calling code can
  pass it positionally or by keyword.

- [ ] **Step 1: Add the `json` import**

At the top of `src/local_eval.py`, alongside the existing `import math`:

```python
import json
import math
```

- [ ] **Step 2: Extend `run_matchup`'s signature and engine import**

Change:

```python
def run_matchup(rb, candidate_dir: Path, opponent_dir: Path, battles: int, engine_dir: Path):
    sys.path.insert(0, str(engine_dir))
    from cg.game import battle_start, battle_select, battle_finish
```

to:

```python
def run_matchup(rb, candidate_dir: Path, opponent_dir: Path, battles: int, engine_dir: Path,
                 save_losses_dir: Path | None = None):
    sys.path.insert(0, str(engine_dir))
    from cg.game import battle_start, battle_select, battle_finish, visualize_data
```

- [ ] **Step 3: Track per-step obs/action logs and dump losses**

Change the battle loop body from:

```python
        obs, start_data = battle_start(deck_a, deck_b)
        if obs is None:
            errors += 1
            continue

        agents = [agent_a, agent_b]
        while obs["current"]["result"] == -1:
            your_index = obs["current"]["yourIndex"]
            select_list = agents[your_index](obs)
            obs = battle_select(select_list)

        winner_slot = obs["current"]["result"]
        winner_is_candidate = (winner_slot == 0) == candidate_first
        if winner_is_candidate:
            wins += 1
        battle_finish()
```

to:

```python
        obs, start_data = battle_start(deck_a, deck_b)
        if obs is None:
            errors += 1
            continue

        agents = [agent_a, agent_b]
        obs_log = [""] if save_losses_dir else None
        action_log = [None] if save_losses_dir else None
        while obs["current"]["result"] == -1:
            your_index = obs["current"]["yourIndex"]
            select_list = agents[your_index](obs)
            if save_losses_dir:
                obs.pop("search_begin_input", None)
                obs_log.append(obs)
                action_log.append(select_list)
            obs = battle_select(select_list)

        winner_slot = obs["current"]["result"]
        winner_is_candidate = (winner_slot == 0) == candidate_first
        if winner_is_candidate:
            wins += 1
        elif save_losses_dir:
            vis = json.loads(visualize_data())
            for step in range(len(vis)):
                vis[step]["obs"] = obs_log[step]
                vis[step]["action"] = [action_log[step], action_log[step]]
            save_losses_dir.mkdir(parents=True, exist_ok=True)
            out_path = save_losses_dir / f"{opponent_dir.name}_battle{i}.json"
            out_path.write_text(json.dumps(vis))
        battle_finish()
```

(`visualize_data()` must be called before `battle_finish()` — confirmed by the reference kernel's
ordering. `.pop("search_begin_input", None)` uses the safe two-arg form, not the reference
kernel's bare `.pop(...)`, since not every observation is guaranteed to carry that key.)

- [ ] **Step 4: Wire the CLI flag through `main()`**

Change:

```python
    parser.add_argument("--battles", type=int, default=30, help="Battles per matchup (default 30)")
    args = parser.parse_args()
```

to:

```python
    parser.add_argument("--battles", type=int, default=30, help="Battles per matchup (default 30)")
    parser.add_argument("--save-losses", help="Directory to dump lost-battle replays as JSON (drag into the community visualizer.html)")
    args = parser.parse_args()
```

and change:

```python
    rb = _load_run_battle_module()
    candidate_dir = Path(args.candidate).resolve()
```

to:

```python
    rb = _load_run_battle_module()
    candidate_dir = Path(args.candidate).resolve()
    save_losses_dir = Path(args.save_losses).resolve() if args.save_losses else None
```

and change the `run_matchup` call site from:

```python
        wins, errors, games = run_matchup(rb, candidate_dir, opponent_dir, args.battles, engine_dir)
```

to:

```python
        wins, errors, games = run_matchup(rb, candidate_dir, opponent_dir, args.battles, engine_dir, save_losses_dir)
```

- [ ] **Step 5: Verify losses get dumped**

Run:
```bash
rm -rf /tmp/eval_losses
python src/local_eval.py --candidate submissions/kiyota_mega_lucario_ex --opponents submissions/masamikobayashi_archaludon_cinderace --battles 10 --save-losses /tmp/eval_losses
ls /tmp/eval_losses
```
Expected: `kiyota_mega_lucario_ex` is a weaker candidate per `baseline-comparison.md`'s real
scores (Lucario 490.8 vs. Archaludon 643.1), so it should lose at least one of the 10 games
against `masamikobayashi_archaludon_cinderace` — `ls` should show at least one
`masamikobayashi_archaludon_cinderace_battleN.json` file. Confirm one file parses as JSON and is
a non-empty list:
```bash
python3 -c "import json; d = json.load(open(sorted(__import__('pathlib').Path('/tmp/eval_losses').glob('*.json'))[0])); print(len(d), list(d[1].keys()))"
```
Expected: prints a length > 1 and a key list that includes `obs` and `action`.

- [ ] **Step 6: Verify default behavior (no flag) is unaffected**

Run: `python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 4`
Expected: same 5-row table shape as Task 2's verification, no new output, no files written
anywhere (the `if save_losses_dir` branches are all skipped when the flag is omitted since it
defaults to `None`).

- [ ] **Step 7: Commit**

```bash
git add src/local_eval.py
git commit -m "$(cat <<'EOF'
Add --save-losses replay capture to local_eval.py

Dumps cg.game.visualize_data() output for every candidate loss,
in the format the community's existing visualizer.html expects,
so a losing matchup can be inspected instead of re-run blind.
EOF
)"
```

---

### Task 4: `--repeats N` stability check

**Files:**
- Modify: `src/local_eval.py` — add a `check_stability` helper function (near `wilson_interval`,
  currently `src/local_eval.py:40-47`); modify `main()`'s matchup loop and print loop.

**Interfaces:**
- Consumes: `wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]` (already
  defined, unchanged).
- Produces: `check_stability(repeat_results: list[tuple[int, int]]) -> bool` — `repeat_results`
  is a list of `(wins, games)` pairs, one per repeat; returns `True` if every repeat's win-rate
  point estimate falls inside every other repeat's Wilson 95% CI, `False` otherwise.

- [ ] **Step 1: Add the `check_stability` helper**

Directly below the existing `wilson_interval` function in `src/local_eval.py`:

```python
def check_stability(repeat_results: list[tuple[int, int]]) -> bool:
    if len(repeat_results) < 2:
        return True
    rates = [wins / games if games else 0.0 for wins, games in repeat_results]
    cis = [wilson_interval(wins, games) if games else (0.0, 0.0) for wins, games in repeat_results]
    for i, rate in enumerate(rates):
        for j, (lo, hi) in enumerate(cis):
            if i != j and not (lo <= rate <= hi):
                return False
    return True
```

- [ ] **Step 2: Add the `--repeats` CLI flag**

Change:

```python
    parser.add_argument("--save-losses", help="Directory to dump lost-battle replays as JSON (drag into the community visualizer.html)")
    args = parser.parse_args()
```

to:

```python
    parser.add_argument("--save-losses", help="Directory to dump lost-battle replays as JSON (drag into the community visualizer.html)")
    parser.add_argument("--repeats", type=int, default=1, help="Independent repeats per matchup, to check ranking stability (default 1)")
    args = parser.parse_args()
```

- [ ] **Step 3: Run `--repeats` independent repeats per opponent and pool them**

Change the matchup loop from:

```python
    total_wins, total_games = 0, 0
    rows = []
    for opponent_dir in opponents:
        wins, errors, games = run_matchup(rb, candidate_dir, opponent_dir, args.battles, engine_dir, save_losses_dir)
        lo, hi = wilson_interval(wins, games) if games else (0.0, 0.0)
        rows.append((opponent_dir.name, wins, games, errors, lo, hi))
        total_wins += wins
        total_games += games
```

to:

```python
    total_wins, total_games = 0, 0
    rows = []
    for opponent_dir in opponents:
        repeat_results = []
        pooled_errors = 0
        for _ in range(args.repeats):
            wins, errors, games = run_matchup(rb, candidate_dir, opponent_dir, args.battles, engine_dir, save_losses_dir)
            repeat_results.append((wins, games))
            pooled_errors += errors
        pooled_wins = sum(w for w, g in repeat_results)
        pooled_games = sum(g for w, g in repeat_results)
        stable = check_stability(repeat_results)
        lo, hi = wilson_interval(pooled_wins, pooled_games) if pooled_games else (0.0, 0.0)
        rows.append((opponent_dir.name, pooled_wins, pooled_games, pooled_errors, lo, hi, stable, repeat_results))
        total_wins += pooled_wins
        total_games += pooled_games
```

- [ ] **Step 4: Print the stability column and per-repeat breakdown only when `--repeats > 1`**

Change the print block from:

```python
    print(f"{'opponent':<40} {'wins':>6} {'games':>6} {'errors':>7} {'win%':>7} {'95% CI':>16}")
    for name, wins, games, errors, lo, hi in rows:
        pct = wins / games * 100 if games else 0.0
        print(f"{name:<40} {wins:>6} {games:>6} {errors:>7} {pct:>6.1f}% [{lo*100:>5.1f}, {hi*100:>5.1f}]")
```

to:

```python
    if args.repeats > 1:
        print(f"{'opponent':<40} {'wins':>6} {'games':>6} {'errors':>7} {'win%':>7} {'95% CI':>16} {'stable':>10}")
    else:
        print(f"{'opponent':<40} {'wins':>6} {'games':>6} {'errors':>7} {'win%':>7} {'95% CI':>16}")
    for name, wins, games, errors, lo, hi, stable, repeat_results in rows:
        pct = wins / games * 100 if games else 0.0
        line = f"{name:<40} {wins:>6} {games:>6} {errors:>7} {pct:>6.1f}% [{lo*100:>5.1f}, {hi*100:>5.1f}]"
        if args.repeats > 1:
            line += f" {'OK' if stable else 'UNSTABLE':>10}"
        print(line)
        if args.repeats > 1:
            per_repeat = ", ".join(
                f"{w}/{g} ({w / g * 100:.1f}%)" if g else "0/0" for w, g in repeat_results
            )
            print(f"{'':<40} repeats: {per_repeat}")
```

(This keeps default-invocation output byte-for-byte identical to before Task 4, per the Global
Constraints: at `--repeats 1`, the header, row format, and absence of a per-repeat line are all
unchanged from Task 3's version.)

- [ ] **Step 5: Verify default behavior (`--repeats` omitted) is unaffected**

Run: `python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 4`
Expected: identical output shape to Task 3 Step 6 — no `stable` column, no `repeats:` lines.

- [ ] **Step 6: Verify `--repeats` runs multiple times and pools correctly**

Run: `python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 10 --repeats 3`
Expected: each opponent row now has a `stable` column (`OK` or `UNSTABLE`) and a `repeats:` line
listing 3 `wins/games (pct%)` entries below it; the row's own `games` total equals 3× the number
of non-error games from a single repeat (i.e., pooling happened); the final pooled line at the
bottom reflects the sum across all opponents' pooled games, not just one repeat's worth.

- [ ] **Step 7: Verify the `UNSTABLE` flag actually fires at least once**

Run: `python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 2 --repeats 5`
Expected: with only 2 games per repeat, Wilson CIs are wide but point estimates (0%, 50%, 100%)
swing hard between repeats — at least one opponent row should print `UNSTABLE`. If every row
prints `OK` even here, re-check `check_stability`'s comparison logic before considering this task
done (it may be silently always returning `True`).

- [ ] **Step 8: Commit**

```bash
git add src/local_eval.py
git commit -m "$(cat <<'EOF'
Add --repeats stability check to local_eval.py

Runs each matchup N independent times and flags UNSTABLE when
repeat win-rate point estimates fall outside each other's Wilson
CI, answering whether the default 30-games/matchup count is
actually enough to trust a single reading.
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** all three design sections (expand roster / replay capture / stability
  check) map 1:1 to Tasks 2/3/4; the spec's setup note maps to Task 1.
- **Type consistency:** `run_matchup`'s new `save_losses_dir` parameter (Task 3) is threaded
  through unchanged into Task 4's repeat-calling loop; `check_stability`'s `repeat_results` type
  (`list[tuple[int, int]]`, i.e. `(wins, games)` without `errors`) matches exactly how Task 4
  Step 3 builds it before calling `check_stability(repeat_results)`.
- **No placeholders:** every step shows the literal before/after code, not a description of the
  change.
