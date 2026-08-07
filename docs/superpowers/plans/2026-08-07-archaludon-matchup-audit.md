# Archaludon Matchup-Logic Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find and fix concrete, evidence-based bugs in `submissions/masamikobayashi_archaludon_cinderace/main.py`'s matchup-specific scoring logic (Crustle/Alakazam/Hop branches and the shared `detect_matchup`/estimation helpers) — the densest, least-tested code in the agent — using the same rigor that found the `random.sample` fix worth +128.5 real ladder points (643.1 → 771.6).

**Architecture:** This is an audit of an existing rule-based scorer, not new-feature development. Each task investigates one logic area by tracing it against real observation data from the actual `cg` engine (self-play via `run_battle.py`'s loader, or replay JSONs already downloaded to `data/raw/episodes/`), confirms whether a hypothesized defect is real, and — only if confirmed — applies a minimal fix and re-verifies. "Tests" here are diagnostic scripts run against the real engine, not unit tests with mocked state, because the object being audited is a heuristic tuned against real game shapes, and every prior confirmed bug this session (`episode_pipeline.py`'s step-pairing, the `random.sample` clip) was found this way, not by reading code in isolation.

**Tech Stack:** Python 3, the competition's own `cg` engine (`data/raw/sample_submission/sample_submission/cg`), `run_battle.py` / `local_eval.py` (already in this repo).

## Global Constraints

- `submissions/` is gitignored by design (third-party-derived agent code) — fixes to `main.py` are never committed to git directly. Only the *findings* (what was checked, what was fixed, why) go into `notebooks/kaggle-research/baseline-comparison.md`, which is tracked.
- Never speculatively rewrite scoring logic without first confirming a defect against real engine behavior — this file's whole premise (per direct user instruction) is "evidence-based bugs, not busywork."
- After any fix, `python .claude/skills/run-battle/scripts/run_battle.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 10` must still show a clean 10/10-or-reasonable result with zero `errors:` — treat any regression as a stop condition, revert, and re-diagnose.
- Only 2 Kaggle submissions remain today (2026-08-07) and the competition ends 2026-08-16 — do not spend a submission on this until at least one confirmed, fixed, locally-verified defect is found. Local win rate alone (`local_eval.py`) is known to be unreliable for close comparisons (documented in `baseline-comparison.md`) — it's a sanity gate here, not the basis for claiming the fix works.

---

## File Structure

- **Modify:** `submissions/masamikobayashi_archaludon_cinderace/main.py` — the only file actually changed by any fix in this plan.
- **Modify:** `notebooks/kaggle-research/baseline-comparison.md` — append findings (this file's edits ARE committed to git, unlike the agent code).
- **No new persisted files.** Diagnostic scripts are one-off `python3 -c "..."` invocations run via Bash and discarded, matching this session's established pattern (`git log` shows every prior audit this session — the pairing-bug check, the `SETUP_BENCH_POKEMON` minCount check — was done this way, not saved as a script). If a diagnostic proves reusable across tasks, note that explicitly in the task rather than assuming it.

**Key functions already located in `main.py` (exact names/lines as of this plan's writing — re-`grep` if the file has changed):**
- `my_state(obs)` (line 176) / `opp_state(obs)` (line 180) → `obs.current.players[yourIndex]` / `[1 - yourIndex]`
- `active_pokemon(obs)` (184) / `opp_active_pokemon(obs)` (189) — both already guard `ps.active[0] if ps.active else None` (safe against `None` or empty list)
- `opp_bench_pokemon(obs)` (194) — `[p for p in opp_state(obs).bench if p]`
- `all_my_pokemon(obs)` (197) — `[p for p in (ps.active + ps.bench) if p]` — **unguarded concatenation, own side**
- `detect_matchup(obs)` (425) — `ids = {p.id for p in (opp.active + opp.bench) if p}` — **unguarded concatenation, opponent side**
- `_estimate_alakazam(obs)` (418) / `_estimate_alakazam_from_pokes(opp, pokes)` (400) — Powerful Hand damage floor/ceiling estimate
- `opp_max_damage(obs)` (441) — calls `detect_matchup`, branches per archetype
- `should_skip_ice_cream(obs, active)` (556) — per-matchup HP threshold table `_ICE_CREAM_HP_THRESHOLD` (line ~547)
- Crustle override block starts at line 467 (`if detect_matchup(obs) != "crustle": ...`)
- Hop/Snorlax Boss's Orders logic at lines 665-681 (inside the `BOSS` scoring branch)
- Night Stretcher urgency check at lines 626-636

---

## Task 1: Confirm or rule out the `detect_matchup` face-down-active crash

Per the competition's own `cg/api.py`, `PlayerState.active` is typed `list[Pokemon] | None`, and is documented `None` specifically when *the opponent's* active is face-down (a real, reachable state — e.g. certain setup timings or effects). `detect_matchup` (line 427) does `opp.active + opp.bench` with no `None` guard, unlike `active_pokemon`/`opp_active_pokemon` which already guard this correctly two lines above it. If `opp.active` is ever `None` when `detect_matchup` runs, this raises `TypeError: unsupported operand type(s) for +: 'NoneType' and 'list'`. Because `detect_matchup` is called from many scoring branches (Crustle overrides, `opp_max_damage`, `should_skip_ice_cream`'s Alakazam branch), a single crash here means **every option in that decision falls through to the per-option `except Exception` fallback (score -999999)** — the decision still resolves (nothing crashes the game, per the already-verified-safe per-option isolation), but the agent makes an effectively-blind, worst-case-scored choice for that entire turn, at exactly the moments matchup-awareness matters most.

`all_my_pokemon` (line 197) has the identical unguarded pattern but operates on **your own** side, where `active` should always be visible (the face-down state is opponent-specific per the API's own comment) — lower priority to check, included as a stretch goal at the end of this task rather than a separate task.

**Files:**
- Modify: `submissions/masamikobayashi_archaludon_cinderace/main.py:425-438` (fix, only if confirmed), `:197-198` (stretch)

**Interfaces:**
- Consumes: nothing from other tasks (first task).
- Produces: a confirmed-or-ruled-out verdict on this specific hypothesis, feeding directly into whether Task 1's fix ships. No other task depends on this one's outcome, but if confirmed, re-run Tasks 2-4's diagnostics after the fix since a crash here could have been masking or distorting what those tasks observe.

- [ ] **Step 1: Check whether `active: None` actually appears in real data we already have**

Run against the 299 already-downloaded episode replays (fast, no new download):

```bash
python3 -c "
import json, glob
count_none = 0
count_total = 0
for fp in glob.glob('data/raw/episodes/2026-08-06/*.json')[:50]:
    data = json.load(open(fp))
    for step in data['steps']:
        for entry in step:
            obs = entry.get('observation')
            if not obs or not obs.get('current'):
                continue
            for p in obs['current'].get('players', []):
                count_total += 1
                if p.get('active') is None:
                    count_none += 1
print(f'{count_none}/{count_total} player-states had active=None')
"
```

Expected: a nonzero `count_none` confirms the state is real and reachable, not theoretical. If it's exactly 0 across all 50 files, don't conclude the bug is impossible — proceed to Step 2 regardless, since 50 files is a small sample and the state may be rare (e.g. only mid-effect-resolution).

- [ ] **Step 2: Reproduce the crash directly with a synthetic call**

```bash
python3 -c "
import sys
sys.path.insert(0, 'submissions/masamikobayashi_archaludon_cinderace')
sys.path.insert(0, 'data/raw/sample_submission/sample_submission')
import main as agent_main
from cg.api import to_observation_class

# Minimal fabricated obs matching the real shape, active=None on the opponent side.
fake = {
    'select': {'type': 0, 'context': 0, 'minCount': 1, 'maxCount': 1, 'option': [{'type': 14}],
               'deck': None, 'contextCard': None, 'effect': None,
               'remainDamageCounter': 0, 'remainEnergyCost': 0},
    'current': {
        'turn': 5, 'turnActionCount': 1, 'yourIndex': 0, 'firstPlayer': 0,
        'energyAttached': False, 'supporterPlayed': False, 'stadiumPlayed': False,
        'retreated': False, 'stadium': None, 'looking': None, 'result': -1,
        'players': [
            {'active': [{'id': 190, 'serial': 1, 'hp': 300, 'maxHp': 300, 'appearThisTurn': False,
                         'energies': 3, 'energyCards': [], 'tools': [], 'preEvolution': []}],
             'bench': [], 'benchMax': 3, 'deckCount': 40, 'discard': [], 'hand': [], 'handCount': 3,
             'prize': [None]*6},
            {'active': None, 'bench': [], 'benchMax': 3, 'deckCount': 40, 'discard': [],
             'hand': None, 'handCount': 3, 'prize': [None]*6},
        ],
    },
    'logs': [], 'remainingOverageTime': 600, 'search_begin_input': None, 'step': 5,
}
obs = to_observation_class(fake)
try:
    result = agent_main.detect_matchup(obs)
    print('NO CRASH — returned:', result)
except TypeError as e:
    print('CONFIRMED CRASH:', e)
"
```

Expected: either `CONFIRMED CRASH: unsupported operand type(s) for +: 'NoneType' and 'list'`, or `NO CRASH` if `to_observation_class` itself normalizes `None` to `[]` on the way in (check the `cg/api.py` `to_dataclass` helper if this happens — that would mean the raw-dict layer protects against it and this task ends here, confirmed *not* a real bug).

- [ ] **Step 3: If confirmed, apply the minimal fix**

```python
def detect_matchup(obs):
    opp = opp_state(obs)
    ids = {p.id for p in ((opp.active or []) + (opp.bench or [])) if p}
    if ids & CRUSTLE_LINE:
        return "crustle"
    if ids & HOP_LINE:
        return "hop"
    if ids & STARMIE_LINE:
        return "starmie"
    if ids & LUCARIO_LINE:
        return "lucario"
    if ids & ALAKAZAM_LINE:
        return "alakazam"
    return "generic"
```

(Only the `ids = {...}` line changes — wrap both sides in `(... or [])`.)

- [ ] **Step 4: Re-run Step 2's synthetic reproduction to confirm the fix**

Same script as Step 2. Expected: `NO CRASH — returned: generic` (no matchup line present in the fabricated bench/active, so `generic` is correct).

- [ ] **Step 5: Stretch — apply the same guard to `all_my_pokemon` (line 197-198) for consistency**

```python
def all_my_pokemon(obs):
    ps = my_state(obs)
    return [p for p in ((ps.active or []) + (ps.bench or [])) if p]
```

Lower-confidence fix (own-side `active` is less likely to be `None` per the API's own comment being opponent-specific) — apply only if Step 3 is applied, for defensive consistency, not because it's independently confirmed.

- [ ] **Step 6: Regression check**

```bash
python3 .claude/skills/run-battle/scripts/run_battle.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 10
```

Expected: 10/10 or similar clean result, zero `errors:` line. If this task made no changes (crash didn't reproduce), skip this step — nothing changed.

---

## Task 2: Audit the Crustle override block for logic that references `opp_max_damage`/`detect_matchup` results inconsistently

**Files:**
- Modify: `submissions/masamikobayashi_archaludon_cinderace/main.py:459-524` (Crustle override block)

**Interfaces:**
- Consumes: Task 1's fix, if applied (this block calls `detect_matchup` at line 467 and would have been affected by the same crash).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Extract every real Crustle-matchup decision from the downloaded episode data**

We don't have replay data of *this exact agent* playing (episodes are other teams' games), so instead trace this agent's own decisions in self-play against a Crustle-piloting opponent. Check whether any pulled kernel/opponent in `submissions/` actually plays Crustle — if none does, build a minimal synthetic Crustle-line active/bench (card IDs from `CRUSTLE_LINE`, check via `grep -n "CRUSTLE_LINE = " submissions/masamikobayashi_archaludon_cinderace/main.py` for the exact set) and drive a few turns via direct `score_option` calls rather than a full self-play loop, since no real Crustle opponent is locally available yet:

```bash
grep -n "CRUSTLE_LINE = \|HOP_LINE = \|ALAKAZAM_LINE = \|STARMIE_LINE = \|LUCARIO_LINE = " submissions/masamikobayashi_archaludon_cinderace/main.py
```

Read the printed card ID sets before writing the synthetic observation in Step 2 — do not guess IDs.

- [ ] **Step 2: Build one synthetic mid-game observation with a Crustle-line Pokemon on the opponent's board, at a decision point that hits each of the override's branches**

Reuse Task 1 Step 2's fabrication pattern, but set `players[1]['active']` to a real Crustle-line card ID (from Step 1's grep output) instead of `None`, and vary `players[0]['active']`'s `id`/`hp`/`energies` across three separate calls to hit: (a) the "don't evolve to ex" branch (line 476), (b) the "Metal Defender does 0" branch (line 490), (c) the "Raging Hammer" branch (line 493). For each, call `score_option(obs, opt)` directly (import path as in Task 1 Step 2) with an `opt` matching that branch's expected `OptionType`/`cid`, and print the returned `(score, reason)`.

- [ ] **Step 3: Compare each returned reason string against the branch you intended to hit**

If `reason` doesn't match (e.g. you intended to hit "Crustle: Metal Defender does 0" but got a different string back), that means an earlier condition in the `if/elif` chain is shadowing the one you're testing — trace which condition evaluates true first and decide whether that's correct given the fabricated state, or a genuine ordering bug.

- [ ] **Step 4: If a real ordering/shadowing bug is found, fix the minimal condition and re-run Step 2's specific case to confirm the correct branch now fires.**

(No generic code here — the fix depends entirely on what Step 3 finds. Do not apply a fix speculatively if Step 3 finds nothing wrong.)

- [ ] **Step 5: Regression check** (same command as Task 1 Step 6).

---

## Task 3: Audit `_estimate_alakazam`'s Powerful Hand damage estimate for a stale-state bug

**Files:**
- Modify: `submissions/masamikobayashi_archaludon_cinderace/main.py:400-422`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Read the full `_ALA_BOARD_GAIN` table and the `enriching_seen` check (lines around 400-415) to understand what "gain" is supposed to represent**

```bash
grep -n "_ALA_BOARD_GAIN" -A 10 submissions/masamikobayashi_archaludon_cinderace/main.py
```

- [ ] **Step 2: Check the `enriching_seen` OR-condition for a scope bug**

Line 408-410 checks card id `13` in `opp.discard` OR in any bench/active Pokemon's `energyCards`. Card id `13` is referenced without a named constant elsewhere in this function (unlike `ALAKAZAM_LINE`, `HOP_SNORLAX`, etc. which are named). Confirm what card `13` actually is:

```bash
grep "^13," "data/raw/EN Card Data.csv"
```

If it's not the card the "enriching" comment implies (cross-check against the comment/docstring context immediately above line 407, and the deck's actual Alakazam-relevant tech cards), this is a real bug — the wrong card ID is being checked, meaning the "have we seen the enabler" heuristic is silently checking for the wrong card the entire game. If it does match, no bug — move to Step 3.

- [ ] **Step 3: Check whether `_estimate_alakazam` reads from a stale `opp_bench_pokemon` snapshot vs. the live one used elsewhere**

`_estimate_alakazam` (line 418-422) builds `pokes` from `opp.active + opp.bench` directly (not via the safer `opp_bench_pokemon(obs)` helper at line 194, which filters `None` entries) — check whether `opp.bench` can contain `None` placeholders for empty bench slots (per the API, bench slots for unfilled positions may be `None` rather than the list being shorter). If so, `pokes` here would include `None` entries, and line 402 `ids = [p.id for p in pokes if p]` already filters them — so this specific path is actually safe (the `if p` guard is there). Confirm this is genuinely safe and move on; don't apply a speculative fix if the guard already covers it.

- [ ] **Step 4: If Step 2 found a real wrong-card-ID bug, fix it and re-verify**

Fix pattern (exact fix depends on what the correct card ID actually is, from Step 2's CSV lookup):

```python
enriching_seen = (
    any(c and c.id == <CORRECT_ID> for c in (opp.discard or []))
    or any(c and c.id == <CORRECT_ID> for p in pokes if p for c in (getattr(p, "energyCards", None) or []))
)
```

- [ ] **Step 5: Regression check** (same command as Task 1 Step 6).

---

## Task 4: Audit the Hop/Snorlax Boss's Orders targeting logic for the `active.id` equality checks

**Files:**
- Modify: `submissions/masamikobayashi_archaludon_cinderace/main.py:665-681`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Re-read the two branches (Cinderace-active vs Archaludon-active) and confirm the HP threshold `220` in `active.hp > 220` is checked against current HP or max HP**

```bash
grep -n "class Pokemon" -A 12 data/raw/sample_submission/sample_submission/cg/api.py
```

Confirm whether `Pokemon.hp` in the real dataclass represents *current* HP (damaged) or the card's printed max HP. If `main.py`'s `active.hp` at line 677 is being compared against `220` intending "is Archaludon ex undamaged enough to survive a counter-hit," but `hp` is actually *current* HP that already reflects prior damage, the comparison is directionally correct (lower current HP = more caution needed, threshold still makes sense) — but if it's *max* HP, the check is meaningless (max HP for Archaludon ex is always 300, per the deck doc comment at the top of the file, so `active.hp > 220` would always be true regardless of actual damage taken, silently disabling the intended caution).

- [ ] **Step 2: If `hp` is max HP (bug confirmed), find the actual current-HP field and fix**

Check the dataclass fields printed in Step 1 for a damage-tracking field (likely `maxHp` alongside `hp`, or a separate damage counter) and compute current HP correctly, e.g. `active.hp - damage_on(active)` if a `damage_on` helper already exists (`grep -n "def damage_on" submissions/masamikobayashi_archaludon_cinderace/main.py` — it's already used elsewhere per the earlier `HEAL` context handler at line 1017, so reuse it rather than reinventing).

- [ ] **Step 3: If Step 1 confirms `hp` is already current HP (not max), this task ends with no fix — document as "checked, confirmed correct" rather than leaving it unresolved.**

- [ ] **Step 4: Regression check** (same command as Task 1 Step 6), only if a fix was applied.

---

## Task 5: Synthesize findings and decide on submission

**Files:**
- Modify: `notebooks/kaggle-research/baseline-comparison.md` (append a dated findings section, following the exact pattern of the existing "Rule-based hardening pass (2026-08-07...)" section already in that file)

**Interfaces:**
- Consumes: the confirmed/ruled-out verdict and any fixes from Tasks 1-4.
- Produces: a go/no-go recommendation on whether to spend one of the 2 remaining daily submissions on this round of fixes.

- [ ] **Step 1: Run the full local sanity pass on the (possibly modified) agent**

```bash
python3 .claude/skills/run-battle/scripts/run_battle.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 20
python3 src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 20
```

Record both outputs.

- [ ] **Step 2: Append findings to `notebooks/kaggle-research/baseline-comparison.md`**

Write a new `## Matchup-logic audit (2026-08-07, second pass)` section listing, for each of Tasks 1-4: what was checked, whether a defect was confirmed, and (if fixed) the exact diff. Follow the existing hardening-pass section's structure and tone (checked-and-safe items get one bullet each; confirmed bugs get a full explanation of the mechanism, not just "fixed a bug").

- [ ] **Step 3: Decide submission**

If at least one Task 1-4 defect was **confirmed and fixed** (not just "checked, found safe"): package and submit following the exact process used for the `random.sample` fix (`py_compile`, tar with required-files validation, `kaggle competitions submit`), using one of the 2 remaining daily slots. If nothing was confirmed (every task ends "checked, already safe"): do not spend a submission — update `baseline-comparison.md` to say so explicitly, and hold the 2 remaining slots for the pending IL/Archaludon 2nd-reading decisions already in flight per `10-day-plan.md`.

---

## Self-Review

**Spec coverage:** User asked for a systematic audit of matchup-specific logic (Crustle, Alakazam, Hop) to find concrete bugs, using the same rigor as the `random.sample` fix, budget-aware (2 submissions left, 9 days left). Task 1 covers the concrete lead already found during planning (unguarded `active` concatenation). Tasks 2-4 cover Crustle, Alakazam, and Hop specifically as named. Task 5 covers documentation and the submission decision. Ice Cream threshold logic and Night Stretcher (mentioned in the original ask) are not separate tasks — they're lower-complexity (a lookup table and one boolean condition respectively, already read during plan-writing and not showing an obvious defect the way the concatenation pattern or the card-ID/HP-field risks do) — flagged here explicitly as **not covered** rather than silently dropped; add as a Task 6 later if Tasks 1-4 finish with budget to spare.

**Placeholder scan:** Every step has a real command or real code, not "add error handling" style placeholders. Task 2 and Task 4 have conditional fix code (exact fix depends on what's found) — this is inherent to an audit task, not a placeholder, and is flagged explicitly rather than hidden.

**Type consistency:** `detect_matchup`, `all_my_pokemon`, `_estimate_alakazam`, `should_skip_ice_cream` are referenced with the same signatures throughout (all take `obs` as first/only positional arg, matching the real file).
