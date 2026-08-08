# IL Agent v3 — Scaled-Up Supervised Imitation Learning Push

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between the current imitation-learning agent's real Kaggle ladder score
(523-531) and the current best rule-based agent (hardened Archaludon, 711-811), by fixing real,
verified gaps in the existing IL pipeline — a guardrail layer, ELO-conditioned training data and
sample weighting, MAIN-decision label-noise (duplicate-option) correction, an energy-gap feature
for ATTACH decisions, and inference-threshold calibration — without touching the rule-based
tracks or attempting RL/tree search.

**Architecture:** One evolving submission candidate, `submissions/il_agent_v3/`, built
incrementally task-by-task on top of the already-working v2 pipeline (same pointwise
scorer-over-legal-options shape, same pure-stdlib export for Kaggle-sandbox compatibility).
Early tasks ship cheap, no-retrain wins (a guardrail layer); later tasks touch the training data
and features and require one final retrain before packaging.

**Tech Stack:** Python stdlib + `scikit-learn`/`pandas`/`numpy`/`joblib` for training only (never
shipped — see Global Constraints), `HistGradientBoostingClassifier`, the competition's own `cg`
engine for local testing.

## Global Constraints

- **Deadline is 2026-08-16.** Budget tasks against whatever `date -u` shows when you start —
  don't assume how many days remain without checking.
- **The Kaggle simulation sandbox has no numpy/pandas/scikit-learn/joblib.** Confirmed by a real
  submission ERROR (see `CLAUDE.md`). Anything shipped in `submissions/il_agent_v3/main.py` must
  import only stdlib + `pure_predictor.py`/`il_features.py` (themselves stdlib-only). Training
  scripts under `src/` may use the full data-science stack — they never ship.
- **`exec()`-without-`__file__` gotcha applies to any new file path lookups** in
  `submissions/il_agent_v3/main.py` — copy the existing guard pattern from
  `submissions/il_agent_v2/main.py` (try `__file__`, guarded by `except NameError`, with
  `/kaggle_simulations/agent/<file>` tried first). Don't reinvent this.
- **Kaggle submission budget: 5/day, resets at UTC midnight (not local date), only ERRORed
  submissions are free.** Only 2 Final Submissions count for placement and must be manually
  selected. Real scores need 24-48h and ≥2 readings before trusting. Do not spend a submission
  on anything that hasn't first cleared its local gate below.
- **Offline per-decision top-1 accuracy does not reliably predict real win rate in this
  project** (demonstrated twice already — see `notebooks/kaggle-research/baseline-comparison.md`
  and the plan at `/Users/aleix.lopez/.claude/plans/option-1-detailed-cryptic-brook.md`). Every
  gate in this plan is keyed to `src/local_eval.py` pooled win rate (with `--repeats` for
  stability), not offline accuracy alone. Offline accuracy is a debugging signal, not a ship/no-ship gate.
- **Do not modify `submissions/masamikobayashi_archaludon_cinderace/` or
  `submissions/kiyota_dragapult_ex/`.** Those tracks are working in parallel and out of scope for
  this plan.
- **Do not implement self-play RL or MCTS/tree search.** Out of scope per an explicit user
  decision (community precedent: discussion #717697 reports MCTS/RL was abandoned in this exact
  game due to imperfect information + a weak value head, and no self-play infrastructure exists
  yet). A supervised-only "filtered self-imitation" step (retrain once on won self-play
  trajectories, no search, no value net) may be proposed as an optional stretch task at the very
  end, only if every gate below has passed with days to spare.
- **`submissions/`, `data/raw/`, `data/processed/`, `models/` are all gitignored — never `git
  add` anything under them.** Only documentation changes (`notebooks/kaggle-research/*.md`,
  `CLAUDE.md`) and `src/*.py` changes get committed.
- **Run `bash .claude/skills/secrets-and-data-guard/scripts/scan.sh` before any `git push`.**
- **Only commit/push, and only submit to Kaggle, when the human partner has explicitly asked for
  it** (or the plan's own gates say a submission is warranted AND the executing session has
  already confirmed this with them) — do not submit autonomously just because a local gate passed.

---

## State of the World (read this before touching anything)

This section exists so a fresh session doesn't have to rediscover any of this by reading code —
it was confirmed by direct file inspection on 2026-08-08, not recalled from memory.

### What's already built and working

- **`src/episode_pipeline.py`** — `extract_records_from_dict(data)` parses one downloaded
  episode JSON into a list of record dicts, one per (player, decision). Uses the *correct*
  `steps[i]` observation / `steps[i+1]` action pairing (a real bug, already fixed and
  tripwire-asserted — `min_count <= len(action) <= max_count` and all action indices in range,
  or the record is dropped and counted in `tripwire_failures`). Each record has keys:
  `episode_id, step, player, select, current, action, actor_team, opp_team, actor_reward, turn,
  actor_deck`. **Does not currently carry a leaderboard score** — that's Task 2 below.
- **`src/episode_stream.py`** — `stream_day(day, lookup, out_path, score_floor=950.0)` downloads
  one day's full episode zip, reads members in-memory (never extracts ~18GB to disk), and
  currently applies a **hard per-episode filter**: keeps the whole episode (both players'
  records) only if *at least one* side's `TeamName` resolves to a leaderboard score ≥ 950. Does
  not currently pass scores into the records themselves. This is Task 2's other half.
- **`src/leaderboard.py`** — `fetch_leaderboard(out_csv)` downloads the full public leaderboard
  CSV via `kaggle competitions leaderboard <slug> -d` (confirmed: 6,497 real teams, not the
  ~12-row `--show` preview). `build_lookup(csv_path)` returns `{normalized_name: score}`, keyed
  by both `TeamName` and each `TeamMemberUserNames` entry, normalized via NFKC + casefold +
  strip. `score_for(lookup, team_name)` does the lookup.
- **`src/features.py`** — turns records into a fixed-width training table. Already implements,
  confirmed by direct read:
  - `resolve_option(option, select, current)` — resolves every `OptionType` (PLAY implicit-hand,
    ATTACH/EVOLVE implicit-source + explicit `inPlayArea`/`inPlayIndex` target, ABILITY,
    CARD-DECK/LOOKING) to `(source_card_id, target_pokemon_dict)`. This was a previously-fixed
    bug (card identity used to resolve to `-1` for 68% of MAIN options) — don't re-break it.
  - `global_features(select, current)` — board-state features (`you_active_hp`,
    `you_bench_count`, `opp_active_hp`, etc.) plus `select_type`/`select_context`/`minCount`/`maxCount`.
  - `option_features(option, select, current, card_data, attack_data, card_attrs, g)` — per-option
    features including `opt_is_lethal` (already implemented: `attack.damage >= opp_active_hp >
    0`), `opt_card_hp`, `opt_card_stage`, `opt_card_retreatCost/ex/megaEx/energyType`,
    `opt_target_hp/maxHp/n_energies/n_tools/appearThisTurn`.
  - `_add_listwise_features(rows)` — already implemented: `opt_n_options_in_decision`,
    `opt_is_only_of_type`, `opt_is_max_damage`, `opt_is_lethal_available_in_decision`.
  - `records_to_rows(records, card_data, attack_data, card_attrs)` — yields `(row_dict, label,
    decision_id)` per (decision, option) row. `label = 1 if i in action else 0` — this exact-index
    labeling is what Task 4 below fixes (duplicate/equivalent options currently only label the
    literal chosen index as positive, not its functional duplicates).
  - `build_dataset(records_path, ...)` — loads a JSONL file, returns `(rows, labels,
    decision_ids)` as parallel lists.
  - `load_card_attrs(csv_path)` reads `data/raw/EN_Card_Attrs.csv`
    (columns: `cardId,cardType,retreatCost,hp,weakness,resistance,energyType,basic,stage1,stage2,ex,megaEx,tera,aceSpec,evolvesFrom,n_attacks`,
    booleans as `"1"`/`"0"` strings) but **only loads `retreatCost, ex, megaEx, tera, energyType,
    weakness, resistance, has_evolvesFrom, n_attacks` into its dict — `basic` is present in the
    CSV but not read.** Task 1 needs it.
  - There is currently **no `attacks` (list of attack IDs per card) column anywhere** —
    `EN_Card_Attrs.csv` only has `n_attacks` (a count). Task 5 needs the actual IDs.
- **`src/train_il_model.py`** — `per_decision_top1_accuracy(model, X, decision_ids, y)` computes
  the metric that matters (decision-level top-1, not row-level). `main()` loads records via
  `build_dataset`, splits with `GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)`
  grouped by decision, trains a `HistGradientBoostingClassifier(max_iter=300, max_depth=6,
  learning_rate=0.08, class_weight="balanced", random_state=0)`, saves `{"model":...,
  "feature_columns": list(X.columns)}` via `joblib.dump`. **No `sample_weight` support exists.**
- **`src/export_pure_predictor.py`** — `export_model(model_path, out_path)` reads
  `model._predictors[i][0].nodes` (a structured numpy array with `feature_idx, num_threshold,
  missing_go_to_left, left, right, is_leaf, value`) and `model._baseline_prediction`, writes
  `{"feature_columns": [...], "baseline": float, "trees": [[node_tuple, ...], ...]}` as plain
  JSON. Already validated bit-for-bit identical to sklearn's own `predict_proba` and confirmed to
  survive the real Kaggle sandbox (submission `55325282` COMPLETEd without erroring).
- **`src/pure_predictor.py`** — `load(json_path)` returns the bundle dict as-is (plain
  `json.load`).  `predict_proba_batch(bundle, feature_rows)` walks each tree via
  `_tree_predict`. **Reads whatever keys the bundle JSON has** — adding new keys (e.g. a
  calibrated `"threshold"`) requires zero changes to this file.
- **`submissions/il_agent_v2/main.py`** — deployed, real-scored (523.1/531.8, submission
  `55325282`). Loads `models/il_scorer_v2_pure.json`, `il_features.py` (a synced copy of
  `src/features.py` — **whenever `src/features.py` changes, re-copy it into
  `submissions/il_agent_v3/il_features.py`, don't let them drift**), and the three CSVs.
  `agent(obs_dict)` scores every legal option, ranks by score, takes everything above
  `_THRESHOLD = 0.5` (a hardcoded module constant, **not calibrated** — the code comment at line
  ~55 says so explicitly), clips to `[minCount, maxCount]`. On exception, falls back to
  `list(range(min(minCount, len(options))))` — never crashes, never returns the full deck list
  mid-game (a previously-fixed, now-regression-tested lesson, see `CLAUDE.md` #730707).
  **There is no guardrail layer at all** — no bench-empty check, no forced-lethal-attack check,
  purely `argmax`-then-threshold. This is confirmed by reading the file fresh, not assumed.
  Deck: the real modal Grimmsnarl ex/Froslass list mined from training data (24% of the sampled
  meta) — same deck as `submissions/il_agent_v2b/` (`diff` confirms byte-identical `deck.csv`).
- **`submissions/il_agent_v2b/`** exists (in the default `local_eval.py` opponent roster) as a
  variant trained on Grimmsnarl-only records (same deck, different training-data subset) —
  **it was never actually submitted to Kaggle** (not in `notebooks/kaggle-research/10-day-plan.md`'s
  submission log; cross-checked against `kaggle competitions submissions -c pokemon-tcg-ai-battle`
  directly). Specific offline-accuracy/local-win-rate numbers comparing v2 vs. v2b that were
  discussed earlier in this project's history were **never written into a committed doc** — treat
  any such recalled numbers as unverified until re-measured with a fresh `local_eval.py` run;
  don't build on them.
- **Data already downloaded**, sizes confirmed via `ls -la`:
  `data/processed/il_records.jsonl` (228MB, the original 299 episodes, no ELO filter),
  `il_records_2026-08-05.jsonl` (3.37GB, one ELO-filtered day via `episode_stream.py`),
  `il_records_combined.jsonl` (3.58GB, the two above concatenated — presumed, not scripted;
  verify with `wc -l` before trusting), `il_records_grimmsnarl.jsonl` (66MB, Grimmsnarl/Froslass
  sides only, feeds `il_scorer_v2b.pkl`).
- **Models already trained**: `models/il_scorer_v1.pkl`, `il_scorer_v2.pkl`, `il_scorer_v2b.pkl`,
  `il_scorer_v2_pure.json` (the exported/deployed one).
- **Task tracker task #26** ("Stage 4a: fix over-selection and cannot-decline bugs") is marked
  `pending` but the fix (threshold-clipped-to-`[minCount,maxCount]`, can return `[]`) is **already
  present in code** — only the threshold *calibration* (Task 2 below) remains. Close #26 as
  superseded by this plan's Task 2, or mark it complete once Task 2 lands.

### Known, confirmed-real gaps this plan closes (not speculative)

1. No guardrail layer in `il_agent_v2/main.py` at all (Task 1).
2. `_THRESHOLD = 0.5` is a guess, never calibrated (Task 2, done last against the final model — see task notes on ordering).
3. Leaderboard score is used only as a per-episode keep/discard filter, never attached to
   records or used for weighting/conditioning (Task 3).
4. No ELO-conditioning features (`actor_score_norm`/`opp_score_norm`) and no `sample_weight` in
   training (Task 3/4 — same underlying data change, different consumers).
5. MAIN decisions with multiple functionally-identical options (e.g. 4x Ultra Ball in hand) only
   label the literal chosen index as positive — the original IL rebuild plan measured this at
   ~9.6% of MAIN decisions, capping theoretical top-1 ceiling at 94.9% (Task 5).
6. No `energy_gap` feature for ATTACH decisions — whether an attachment turns on an attack needs
   a card→attack-IDs mapping that doesn't exist as a file yet (only a count, `n_attacks`) (Task 6).
7. `load_card_attrs` doesn't read the `basic` column that's already sitting in the CSV — cheap
   fix, needed by Task 1's guardrail (Task 1 includes this specific one-line fix).

### Why this order

Task 1 ships a real, cheap, no-retrain fix first — mirrors the single highest-leverage fix found
anywhere in this project (the rule-based Archaludon's unclipped-`random.sample` guard was worth
+128.5 real ladder points; a missing bench/lethal guardrail on the IL agent is the same class of
bug). Tasks 2-6 all touch data/features/training and are naturally sequenced so each is
independently testable before the final retrain in Task 7. Task 2 (threshold calibration) is
listed early in the gap list but scheduled as Task 7 in execution order — calibrating against the
*old* model before its data/features change would be wasted work.

---

### Task 1: Guardrail layer + `is_basic` feature, ship as `il_agent_v3`

**Files:**
- Create: `submissions/il_agent_v3/` (copy of `submissions/il_agent_v2/` — `main.py`, `deck.csv`,
  `EN_Card_Data.csv`, `EN_Attack_Data.csv`, `EN_Card_Attrs.csv`, `il_features.py`, `models/`
  directory containing a copy of `il_scorer_v2_pure.json`)
- Modify: `submissions/il_agent_v3/main.py` (guardrail layer)
- Modify: `submissions/il_agent_v3/il_features.py` (add `basic` to `load_card_attrs`, add
  `opt_card_is_basic` to `option_features`)
- Modify: `src/features.py` (same two changes, kept in sync — this is the source of truth,
  `il_features.py` copies are downstream)

**Interfaces:**
- Consumes: `il_features.load_card_attrs(csv_path)` (existing), `il_features.option_features(...)`
  (existing), `il_features.OPT_PLAY` constant (existing, value `7`).
- Produces: `option_features(...)` now includes `"opt_card_is_basic": int` in its return dict —
  later tasks (and the eventual retrain) may use this as a real model feature too, not just a
  guardrail input.

- [ ] **Step 1: Add `basic` to `load_card_attrs` in `src/features.py`**

```python
def load_card_attrs(csv_path: Path = CARD_ATTRS_CSV) -> dict:
    """cardId -> {retreatCost, ex, megaEx, tera, energyType, weakness, resistance,
    evolvesFrom (bool: has one), n_attacks, basic}"""
    attrs = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                card_id = int(row["cardId"])
            except (ValueError, KeyError):
                continue
            attrs[card_id] = {
                "retreatCost": int(row.get("retreatCost", 0) or 0),
                "ex": int(row.get("ex", 0) or 0),
                "megaEx": int(row.get("megaEx", 0) or 0),
                "tera": int(row.get("tera", 0) or 0),
                "energyType": int(row.get("energyType", -1) or -1),
                "weakness": int(row["weakness"]) if row.get("weakness") not in (None, "", "None") else -1,
                "resistance": int(row["resistance"]) if row.get("resistance") not in (None, "", "None") else -1,
                "has_evolvesFrom": int(bool(row.get("evolvesFrom"))),
                "n_attacks": int(row.get("n_attacks", 0) or 0),
                "basic": int(row.get("basic", 0) or 0),
            }
    return attrs
```

- [ ] **Step 2: Add `opt_card_is_basic` to `option_features` in `src/features.py`**

In the `return { ... }` dict of `option_features`, add one line after `"opt_card_has_evolvesFrom"`:

```python
        "opt_card_has_evolvesFrom": attrs.get("has_evolvesFrom", 0),
        "opt_card_is_basic": attrs.get("basic", 0),
```

- [ ] **Step 3: Verify features.py still runs standalone**

Run: `python3 src/features.py`
Expected: prints `N (decision, option) rows from M decisions`, `positive rate: 0.xxx`, and a
sample row — confirm the sample row dict now contains `"opt_card_is_basic"` as a key.

- [ ] **Step 4: Create `submissions/il_agent_v3/` as a copy of `il_agent_v2`**

```bash
cp -r submissions/il_agent_v2 submissions/il_agent_v3
cp src/features.py submissions/il_agent_v3/il_features.py
```

(The `cp -r` brings along `models/il_scorer_v2_pure.json` unchanged — Task 1 doesn't retrain, it
only adds inference-time logic on top of the existing model. `il_features.py`'s changed functions
are additive — `_FEATURE_COLUMNS` from the old bundle won't reference `opt_card_is_basic`, so
`_score_options`'s `row.get(col, -1)` projection is unaffected; the new field exists purely for
the guardrail to read directly off `rows`, not through the model.)

- [ ] **Step 5: Add the guardrail layer to `submissions/il_agent_v3/main.py`**

Replace the `agent()` function body with a version that computes `rows` and `g` once (needed by
both scoring and the guardrail) and applies two guardrails after thresholding:

```python
def _apply_guardrails(rows, chosen, min_count, max_count, bench_count):
    """Two guardrails, in priority order: take an available lethal attack; otherwise, if the
    bench is completely empty and a Basic Pokemon is playable from hand, play it. Mirrors the
    guardrail pattern already proven on the rule-based agents in this repo (see
    notebooks/kaggle-research/baseline-comparison.md's Dragapult ex Fezandipiti_ex fix and the
    Archaludon random.sample fix — both single-guardrail fixes that moved real ladder score)."""
    lethal_idxs = [i for i, r in enumerate(rows) if r.get("opt_is_lethal")]
    if lethal_idxs and not any(i in chosen for i in lethal_idxs):
        chosen = [lethal_idxs[0]]
    elif bench_count == 0:
        basic_play_idxs = [
            i for i, r in enumerate(rows)
            if r.get("opt_type") == il_features.OPT_PLAY and r.get("opt_card_is_basic")
        ]
        if basic_play_idxs and not any(i in chosen for i in basic_play_idxs):
            chosen = [basic_play_idxs[0]]
    chosen = sorted(set(chosen))
    if len(chosen) > max_count:
        chosen = chosen[:max_count]
    return chosen


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return _read_deck_csv()

    select = obs_dict["select"]
    current = obs_dict["current"]
    options = select.get("option") or []
    if not options:
        return []

    min_count = select.get("minCount", 1) or 1
    max_count = select.get("maxCount", 1) or 1

    try:
        g = il_features.global_features(select, current)
        rows = [
            il_features.option_features(option, select, current, _CARD_DATA, _ATTACK_DATA, _CARD_ATTRS, g)
            for option in options
        ]
        il_features._add_listwise_features(rows)
        feature_rows = [[row.get(col, -1) for col in _FEATURE_COLUMNS] for row in rows]
        scores = pure_predictor.predict_proba_batch(_BUNDLE, feature_rows)

        ranked = sorted(range(len(options)), key=lambda i: scores[i], reverse=True)
        above_threshold = [i for i in ranked if scores[i] > _THRESHOLD]

        if len(above_threshold) < min_count:
            chosen = ranked[:min_count]
        elif len(above_threshold) > max_count:
            chosen = ranked[:max_count]
        else:
            chosen = above_threshold

        chosen = _apply_guardrails(rows, chosen, min_count, max_count, g.get("you_bench_count", 0))

        if min_count == 0 and not chosen:
            return []
        if len(chosen) < min_count:
            # a guardrail can't reduce below minCount; pad with the next-best ranked options
            for i in ranked:
                if i not in chosen:
                    chosen.append(i)
                if len(chosen) >= min_count:
                    break
        return chosen
    except Exception:
        return list(range(min(min_count, len(options))))
```

Remove the old standalone `_score_options` function (folded into `agent()` above so `rows` is
available to the guardrail) and update the module docstring's second paragraph to mention the
guardrail layer.

- [ ] **Step 6: Syntax check**

Run: `python3 -m py_compile submissions/il_agent_v3/main.py`
Expected: no output (success).

- [ ] **Step 7: Local battle smoke test**

Run: `python3 .claude/skills/run-battle/scripts/run_battle.py --candidate submissions/il_agent_v3 --opponent submissions/masamikobayashi_archaludon_cinderace --battles 6`
Expected: completes 6 battles with no exceptions/tracebacks (win/loss counts don't matter yet,
just that it runs).

- [ ] **Step 8: Local pooled eval, compare to v2's baseline**

Run: `python3 src/local_eval.py --candidate submissions/il_agent_v3 --battles 20 --repeats 2`
Expected: pooled win rate reported with a 95% CI; record the number. This task's bar: **pooled
win rate must not be worse than `il_agent_v2`'s last measured pooled rate (47.5%)** — since the
guardrail only forces two specific, narrow, clearly-correct actions (a free lethal KO; filling a
totally empty bench with an available Basic), a regression here would indicate a bug in Step 5,
not a real tradeoff. If it regresses, re-check `_apply_guardrails`' index bookkeeping before
proceeding.

- [ ] **Step 9: Commit**

```bash
git add src/features.py
git commit -m "feat: add opt_card_is_basic feature, needed by il_agent_v3's guardrail layer"
```

(`submissions/il_agent_v3/` itself is gitignored — nothing to add there.)

---

### Task 2: Attach per-side leaderboard scores into training records

**Files:**
- Modify: `src/episode_pipeline.py` (`extract_records_from_dict` signature)
- Modify: `src/episode_stream.py` (`stream_day` — pass real scores through, switch from
  per-episode to per-side keep policy)

**Interfaces:**
- Consumes: `leaderboard.score_for(lookup, team_name)` (existing, unchanged).
- Produces: every record dict now has `"actor_score": float | None` and `"opp_score": float |
  None` keys. `extract_records_from_dict(data, scores=None)` — `scores`, if given, is `[score0,
  score1]` in absolute player-index order (not per-record actor/opp order — the function does
  that reindexing itself). Backward compatible: `scores=None` (the default, used by
  `episode_pipeline.py`'s own CLI path over already-downloaded local episodes with no leaderboard
  join) leaves both new fields `None` on every record, which downstream (Task 3) must treat as
  "unknown, use the neutral default."

- [ ] **Step 1: Extend `extract_records_from_dict` in `src/episode_pipeline.py`**

```python
def extract_records_from_dict(data: dict, scores: list = None):
    episode_id = data.get("id") or data.get("info", {}).get("EpisodeId")
    steps = data["steps"]
    rewards = data.get("rewards") or [None, None]
    info = data.get("info") or {}
    team_names = info.get("TeamNames") or [None, None]
    decks = [_player_deck(steps, 0), _player_deck(steps, 1)]
    scores = scores or [None, None]

    records = []
    tripwire_failures = 0
    for step_idx in range(len(steps) - 1):
        for player_idx, entry in enumerate(steps[step_idx]):
            if entry.get("status") != "ACTIVE":
                continue
            obs = entry.get("observation")
            if not obs or obs.get("select") is None:
                continue

            select = obs["select"]
            action = steps[step_idx + 1][player_idx].get("action") or []
            min_count = select.get("minCount", 1) or 1
            max_count = select.get("maxCount", 1) or 1
            options = select.get("option") or []

            if action and any(a < 0 or a >= len(options) for a in action):
                tripwire_failures += 1
                continue
            if not (min_count <= len(action) <= max_count):
                tripwire_failures += 1
                continue

            opp_idx = 1 - player_idx
            records.append(
                {
                    "episode_id": episode_id,
                    "step": step_idx,
                    "player": player_idx,
                    "select": select,
                    "current": obs["current"],
                    "action": action,
                    "actor_team": team_names[player_idx] if player_idx < len(team_names) else None,
                    "opp_team": team_names[opp_idx] if opp_idx < len(team_names) else None,
                    "actor_reward": rewards[player_idx] if player_idx < len(rewards) else None,
                    "actor_score": scores[player_idx] if player_idx < len(scores) else None,
                    "opp_score": scores[opp_idx] if opp_idx < len(scores) else None,
                    "turn": (obs["current"] or {}).get("turn"),
                    "actor_deck": decks[player_idx],
                }
            )
    return records, tripwire_failures
```

Also update `extract_records` (the file-path wrapper) — no change needed, it already just calls
`extract_records_from_dict(data)` with default `scores=None`, which is correct for its use case
(no leaderboard context for arbitrary local episode files).

- [ ] **Step 2: Update `stream_day` in `src/episode_stream.py` to compute and pass real scores, and apply a per-side (not per-episode) keep policy**

```python
def stream_day(day: str, lookup: dict, out_path: Path, score_floor: float = SCORE_FLOOR):
    ref = f"kaggle/pokemon-tcg-ai-battle-episodes-{day}"
    zip_dir = Path("data/raw/episode_zips")
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{day}.zip"

    print(f"downloading {ref}...")
    subprocess.run(
        ["kaggle", "datasets", "download", ref, "-p", str(zip_dir)],
        check=True,
    )
    downloaded = zip_dir / f"pokemon-tcg-ai-battle-episodes-{day}.zip"
    if not downloaded.exists():
        candidates = list(zip_dir.glob("*.zip"))
        downloaded = candidates[0]

    kept, seen, tripwire = 0, 0, 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(downloaded) as z, out_path.open("w") as out_f:
        names = [n for n in z.namelist() if n.endswith(".json")]
        for name in names:
            seen += 1
            try:
                data = json.loads(z.read(name))
            except json.JSONDecodeError:
                continue
            team_names = (data.get("info") or {}).get("TeamNames") or [None, None]
            scores = [score_for(lookup, t) for t in team_names]
            keep_sides = {i for i, s in enumerate(scores) if s is not None and s >= score_floor}
            if not keep_sides:
                continue
            kept += 1
            records, tw = extract_records_from_dict(data, scores=scores)
            tripwire += tw
            for r in records:
                if r["player"] in keep_sides:
                    out_f.write(json.dumps(r) + "\n")

    downloaded.unlink(missing_ok=True)
    print(f"{day}: {kept}/{seen} episodes kept (>=1 side score >= {score_floor}), "
          f"{tripwire} tripwire failures -> {out_path}")
    return kept, seen
```

The behavior change from before: previously, if *either* side cleared the floor, **both** sides'
records were kept (the weaker side's moves included as if they were good examples). Now only the
qualifying side(s)' records are kept — this directly implements the original plan's stated
curation policy ("drop a side if its leaderboard score < 950 ... drop the episode only if both
sides fail") which was written down but never actually implemented in code until now.

- [ ] **Step 3: Validate on a small real pull**

Run: `python3 src/leaderboard.py --out data/raw/leaderboard.csv` (re-fetch — leaderboard scores
are current, not as-of-episode, and this data is now a day old).

Run: `python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, 'src')
from episode_stream import stream_day
from leaderboard import build_lookup
lookup = build_lookup(Path('data/raw/leaderboard.csv'))
stream_day('2026-08-05', lookup, Path('/tmp/test_scores.jsonl'))
import json
lines = open('/tmp/test_scores.jsonl').readlines()[:5]
for l in lines:
    r = json.loads(l)
    print(r['player'], r['actor_score'], r['opp_score'], r['actor_team'])
"`

Expected: 5 printed lines, each with a non-`None` `actor_score` >= 950.0 (since every kept record
belongs to a side that cleared the floor) — this is the concrete proof the join actually landed
in the record, not just used for filtering.

- [ ] **Step 4: Commit**

```bash
git add src/episode_pipeline.py src/episode_stream.py
git commit -m "feat: attach per-side leaderboard scores to IL records, switch to per-side keep policy"
```

---

### Task 3: ELO-conditioning features and sample weighting

**Files:**
- Modify: `src/features.py` (`global_features`, `records_to_rows`, `build_dataset` signatures;
  new helper `_score_norm`, new helper `sample_weight`)
- Modify: `src/train_il_model.py` (use the new weights)

**Interfaces:**
- Consumes: `rec.get("actor_score")`, `rec.get("opp_score")`, `rec.get("actor_reward")` from
  Task 2's records (may be `None` for the original 299-episode data, predating this join — must
  degrade gracefully, not crash).
- Produces: `global_features(select, current, actor_score=None, opp_score=None)` — two new keys
  `"actor_score_norm"`, `"opp_score_norm"` in its return dict. `records_to_rows(...)` now yields
  4-tuples `(row, label, decision_id, weight)` instead of 3-tuples. `build_dataset(...)` now
  returns `(rows, labels, decision_ids, weights)` instead of 3 lists. **This is a breaking
  signature change** — `train_il_model.py` (this task) and `submissions/il_agent_v3/main.py`
  (already updated in Task 1 to call `il_features.global_features(select, current)` with no
  score args, which is fine — the two new params default to `None`, giving the neutral inference
  value) both need to still work after this change.

- [ ] **Step 1: Add `_score_norm` and `sample_weight` helpers to `src/features.py`**

Add near the top of the file, after the `AREA_*`/`OPT_*` constants:

```python
NEUTRAL_SCORE = 1150.0  # "how would a ~1150-rated player play" — used at inference (no real
                          # opponent score is knowable mid-game) and for training records with
                          # no leaderboard join (the original 299-episode data, pre-Task-2).


def _score_norm(score) -> float:
    s = score if score is not None else NEUTRAL_SCORE
    return (s - 1000.0) / 200.0


def sample_weight(actor_score, actor_reward) -> float:
    """Weight training rows toward stronger, winning players. Records with no leaderboard join
    (actor_score is None) get the neutral weight of 1.0 pre-reward-multiplier."""
    base = 1.0 if actor_score is None else max(0.6, min(1.6, 1.0 + (actor_score - 1000.0) / 200.0))
    won = (actor_reward or 0) > 0
    return base * (1.5 if won else 1.0)
```

- [ ] **Step 2: Thread `actor_score`/`opp_score` through `global_features`**

```python
def global_features(select: dict, current: dict, actor_score=None, opp_score=None) -> dict:
    your_index = current.get("yourIndex")
    players = current.get("players", [])
    you = players[your_index] if your_index is not None and your_index < len(players) else {}
    opp_index = 1 - your_index if your_index in (0, 1) else None
    opp = players[opp_index] if opp_index is not None and opp_index < len(players) else {}

    def pokemon_hp(p):
        active = p.get("active") or []
        if not active or active[0] is None:
            return 0.0
        return float(active[0].get("hp", 0) or 0)

    return {
        "turn": current.get("turn", 0) or 0,
        "turnActionCount": current.get("turnActionCount", 0) or 0,
        "energyAttached": int(bool(current.get("energyAttached"))),
        "supporterPlayed": int(bool(current.get("supporterPlayed"))),
        "stadiumPlayed": int(bool(current.get("stadiumPlayed"))),
        "retreated": int(bool(current.get("retreated"))),
        "you_active_hp": pokemon_hp(you),
        "you_bench_count": len(you.get("bench") or []),
        "you_hand_count": you.get("handCount", 0) or 0,
        "you_discard_count": len(you.get("discard") or []),
        "you_deck_count": you.get("deckCount", 0) or 0,
        "you_prize_count": len(you.get("prize") or []),
        "opp_active_hp": pokemon_hp(opp),
        "opp_bench_count": len(opp.get("bench") or []),
        "opp_hand_count": opp.get("handCount", 0) or 0,
        "opp_discard_count": len(opp.get("discard") or []),
        "opp_deck_count": opp.get("deckCount", 0) or 0,
        "opp_prize_count": len(opp.get("prize") or []),
        "select_type": select.get("type", -1),
        "select_context": select.get("context", -1),
        "select_minCount": select.get("minCount", 1) or 1,
        "select_maxCount": select.get("maxCount", 1) or 1,
        "actor_score_norm": _score_norm(actor_score),
        "opp_score_norm": _score_norm(opp_score),
    }
```

- [ ] **Step 3: Thread scores and weights through `records_to_rows` and `build_dataset`**

```python
def records_to_rows(records, card_data: dict, attack_data: dict = None, card_attrs: dict = None):
    """Yield (feature_dict, label, decision_key, weight) for every (decision, option) pair."""
    for rec_idx, rec in enumerate(records):
        select = rec["select"]
        current = rec["current"]
        action = set(rec["action"])
        g = global_features(select, current, rec.get("actor_score"), rec.get("opp_score"))
        w = sample_weight(rec.get("actor_score"), rec.get("actor_reward"))
        options = select.get("option") or []
        rows = [option_features(option, select, current, card_data, attack_data, card_attrs, g) for option in options]
        _add_listwise_features(rows)
        for i, o in enumerate(rows):
            row = {**g, **o}
            label = 1 if i in action else 0
            yield row, label, rec_idx, w


def build_dataset(records_path: str, card_data_path: str = None, attack_data_path: str = None, card_attrs_path: str = None):
    """Load JSONL records and return (rows, labels, decision_ids, weights) as parallel lists."""
    card_data = load_card_data(Path(card_data_path) if card_data_path else CARD_DATA_CSV)
    attack_data = load_attack_data(Path(attack_data_path) if attack_data_path else ATTACK_DATA_CSV)
    card_attrs = load_card_attrs(Path(card_attrs_path) if card_attrs_path else CARD_ATTRS_CSV)
    records = []
    with open(records_path) as f:
        for line in f:
            records.append(json.loads(line))

    rows, labels, decision_ids, weights = [], [], [], []
    for row, label, decision_id, w in records_to_rows(records, card_data, attack_data, card_attrs):
        rows.append(row)
        labels.append(label)
        decision_ids.append(decision_id)
        weights.append(w)
    return rows, labels, decision_ids, weights
```

Update the `if __name__ == "__main__":` block at the bottom to unpack 4 values instead of 3:

```python
if __name__ == "__main__":
    rows, labels, decision_ids, weights = build_dataset("data/processed/il_records.jsonl")
    print(f"{len(rows)} (decision, option) rows from {len(set(decision_ids))} decisions")
    print(f"positive rate: {sum(labels) / len(labels):.3f}")
    print(f"mean sample weight: {sum(weights) / len(weights):.3f}")
    print("sample row:", rows[0])
```

- [ ] **Step 4: Update `src/train_il_model.py` to use `sample_weight`**

```python
    print("building dataset...")
    rows, labels, decision_ids, weights = build_dataset(args.records)
    X = pd.DataFrame(rows)
    y = np.array(labels)
    groups = np.array(decision_ids)
    w = np.array(weights)
    print(f"{len(X)} rows, {len(np.unique(groups))} decisions, positive rate {y.mean():.3f}")

    splitter = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=0)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    w_train = w[train_idx]
    groups_test = groups[test_idx]

    print(f"train: {len(X_train)} rows / {len(np.unique(groups[train_idx]))} decisions, "
          f"test: {len(X_test)} rows / {len(np.unique(groups_test))} decisions")

    model = HistGradientBoostingClassifier(
        max_iter=300,
        max_depth=6,
        learning_rate=0.08,
        class_weight="balanced",
        random_state=0,
    )
    print("training...")
    model.fit(X_train, y_train, sample_weight=w_train)
```

(Everything after this in `main()` — the accuracy printout and `joblib.dump` — stays the same
for now; Task 4 changes the accuracy metric, Task 7 changes what gets saved into the bundle.)

- [ ] **Step 5: Fast-iteration flag — add `--max-records`**

Large retrains (the 3.58GB combined file) are slow to iterate on while debugging these changes.
Add to `src/train_il_model.py`'s `main()`:

```python
    parser.add_argument("--max-records", type=int, default=None,
                         help="Truncate to the first N raw JSONL lines, for fast iteration")
```

And in `build_dataset` (`src/features.py`), add the same optional parameter:

```python
def build_dataset(records_path: str, card_data_path: str = None, attack_data_path: str = None,
                   card_attrs_path: str = None, max_records: int = None):
    card_data = load_card_data(Path(card_data_path) if card_data_path else CARD_DATA_CSV)
    attack_data = load_attack_data(Path(attack_data_path) if attack_data_path else ATTACK_DATA_CSV)
    card_attrs = load_card_attrs(Path(card_attrs_path) if card_attrs_path else CARD_ATTRS_CSV)
    records = []
    with open(records_path) as f:
        for i, line in enumerate(f):
            if max_records is not None and i >= max_records:
                break
            records.append(json.loads(line))
    ...
```

and pass `max_records=args.max_records` from `train_il_model.py`'s call site.

- [ ] **Step 6: Quick sanity run on the small original file**

Run: `python3 src/train_il_model.py --records data/processed/il_records.jsonl --out /tmp/test_v3_model.pkl --max-records 5000`
Expected: completes without error, prints a positive rate and train/test accuracy in a
reasonable range (roughly consistent with the previously-recorded ~60%/53% MAIN accuracy from
before this task — this is a sanity check that nothing broke the pipeline, not a real accuracy
bar on this tiny subsample).

- [ ] **Step 7: Commit**

```bash
git add src/features.py src/train_il_model.py
git commit -m "feat: ELO-conditioning features (actor_score_norm/opp_score_norm) and leaderboard-weighted training samples"
```

---

### Task 4: Fix MAIN duplicate-option label noise

**Files:**
- Modify: `src/features.py` (`records_to_rows` labeling logic)
- Modify: `src/train_il_model.py` (`per_decision_top1_accuracy` — the redundant index-equality
  check silently breaks once duplicate options can both be labeled positive)

**Interfaces:**
- Consumes: the row dicts already produced by `option_features`/`_add_listwise_features`
  (`opt_type`, `opt_card_id`, `opt_target_card_id`, `opt_attackId` — all already present, no new
  fields needed).
- Produces: a `label = 1` on *every* option in a decision that's functionally equivalent to the
  one actually chosen (same type, same resolved card, same target, same attack), not just the
  literal chosen index. `per_decision_top1_accuracy` now treats "predicted option's label is 1"
  as correct, not "predicted index equals the recorded action index."

- [ ] **Step 1: Compute an equivalence signature and use it for labeling in `records_to_rows`**

```python
def _option_signature(row: dict) -> tuple:
    """Two options are functionally equivalent (e.g. 4 copies of Ultra Ball in hand) if they
    have the same type, resolve to the same card, target the same Pokemon, and reference the
    same attack. Index differs (which physical copy), but the decision is the same."""
    return (row["opt_type"], row["opt_card_id"], row.get("opt_target_card_id", -1), row.get("opt_attackId", -1))


def records_to_rows(records, card_data: dict, attack_data: dict = None, card_attrs: dict = None):
    """Yield (feature_dict, label, decision_key, weight) for every (decision, option) pair.
    All options sharing the chosen option's equivalence signature are labeled positive, not just
    the literal chosen index — see _option_signature."""
    for rec_idx, rec in enumerate(records):
        select = rec["select"]
        current = rec["current"]
        action = rec["action"]
        g = global_features(select, current, rec.get("actor_score"), rec.get("opp_score"))
        w = sample_weight(rec.get("actor_score"), rec.get("actor_reward"))
        options = select.get("option") or []
        rows = [option_features(option, select, current, card_data, attack_data, card_attrs, g) for option in options]
        _add_listwise_features(rows)
        chosen_signatures = {_option_signature(rows[i]) for i in action if i < len(rows)}
        for i, o in enumerate(rows):
            row = {**g, **o}
            label = 1 if _option_signature(o) in chosen_signatures else 0
            yield row, label, rec_idx, w
```

(Note `action` is no longer converted to a `set` up front since it's now only used to build
`chosen_signatures` — the direct index membership check `i in action` is gone, replaced by the
signature check, which is the actual point of this task.)

- [ ] **Step 2: Fix `per_decision_top1_accuracy` in `src/train_il_model.py`**

The old code required the predicted index to equal *the specific* recorded action index — with
duplicate options now sharing `label=1`, the model can correctly predict a *different*
functionally-identical option and get unfairly marked wrong. Drop the redundant index-equality
check:

```python
def per_decision_top1_accuracy(model, X: pd.DataFrame, decision_ids: np.ndarray, y: np.ndarray) -> float:
    scores = model.predict_proba(X)[:, 1]
    correct, total = 0, 0
    for dec_id in np.unique(decision_ids):
        mask = decision_ids == dec_id
        dec_scores = scores[mask]
        dec_labels = y[mask]
        if dec_labels.sum() == 0:
            continue  # shouldn't happen, but be defensive
        predicted_idx = np.argmax(dec_scores)
        total += 1
        if dec_labels[predicted_idx] == 1:
            correct += 1
    return correct / total if total else 0.0
```

- [ ] **Step 3: Verify the signature function with a targeted unit check**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from features import _option_signature
a = {'opt_type': 7, 'opt_card_id': 1121, 'opt_target_card_id': -1, 'opt_attackId': -1}
b = {'opt_type': 7, 'opt_card_id': 1121, 'opt_target_card_id': -1, 'opt_attackId': -1}
c = {'opt_type': 7, 'opt_card_id': 140, 'opt_target_card_id': -1, 'opt_attackId': -1}
assert _option_signature(a) == _option_signature(b), 'two Ultra Ball copies should match'
assert _option_signature(a) != _option_signature(c), 'different cards should not match'
print('OK')
"
```
Expected: prints `OK`.

- [ ] **Step 4: Re-run the small sanity training run, compare positive rate**

Run: `python3 src/train_il_model.py --records data/processed/il_records.jsonl --out /tmp/test_v3_model2.pkl --max-records 5000`
Expected: `positive rate` printed should be noticeably **higher** than Task 3 Step 6's run on the
same subsample (more rows are now labeled positive due to equivalence-grouping) — if it's
identical, the signature grouping isn't taking effect and Step 1 needs re-checking.

- [ ] **Step 5: Commit**

```bash
git add src/features.py src/train_il_model.py
git commit -m "fix: label all functionally-equivalent options as positive (MAIN duplicate-option noise), fix top-1 metric to match"
```

---

### Task 5: `energy_gap` feature for ATTACH decisions

**Files:**
- Create: `src/export_card_attacks.py` (generates the card→attack-IDs mapping that doesn't exist
  as a file yet — `EN_Card_Attrs.csv` only has a count, `n_attacks`, not the actual IDs)
- Modify: `data/raw/EN_Card_Attrs.csv` (regenerated with a new `attacks` column, pipe-joined IDs,
  same encoding style as `EN_Attack_Data.csv`'s existing `energies` column)
- Modify: `src/features.py` (`load_card_attrs` reads the new column; `option_features` computes
  `opt_energy_gap_before`/`opt_energy_gap_after` for ATTACH options)

**Interfaces:**
- Consumes: `cg.api.all_card_data()` — each `CardData` has `.cardId` and `.attacks: list[int]`
  (confirmed directly from the competition's own `cg/api.py` docstring/dataclass, not guessed).
  `attack_data` (already loaded by `load_attack_data`, has `energies: list[int]` per attack —
  the *typed* energy list, not just a count).
- Produces: `load_card_attrs(...)`'s per-card dict gains an `"attacks": list[int]` key.
  `option_features(...)` gains `"opt_energy_gap_before"` and `"opt_energy_gap_after"` — for
  `OptionType.ATTACH` options only (`-1` for every other option type): the number of additional
  energy attachments still needed, for the *cheapest* attack among the target Pokemon's known
  attacks, before and after this specific attachment. `0` means "this attachment turns on (or
  keeps turned on) an attack right now."

- [ ] **Step 1: Write `src/export_card_attacks.py`**

This needs to run inside an environment where the competition's `cg` package is importable —
run it from the repo root with the engine directory on `sys.path`, matching the pattern already
used by `.claude/skills/run-battle/scripts/run_battle.py`'s `find_engine_dir`.

```python
"""Regenerate data/raw/EN_Card_Attrs.csv with an added `attacks` column (pipe-joined attack IDs
per card) — the file already has every other column this script reproduces, but was originally
generated ad-hoc with no checked-in script. cg.api.CardData.attacks (list[int]) is exactly what's
needed for the energy_gap feature (does this ATTACH turn on an attack) and didn't exist as a
column before (only n_attacks, a count).

Usage (run from repo root, with an engine-bearing submission directory locatable):
    python src/export_card_attacks.py --engine-dir submissions/masamikobayashi_archaludon_cinderace --out data/raw/EN_Card_Attrs.csv
"""

import argparse
import csv
import sys
from pathlib import Path


def export(engine_dir: str, out_path: str):
    sys.path.insert(0, engine_dir)
    from cg.api import all_card_data

    cards = all_card_data()
    fieldnames = [
        "cardId", "cardType", "retreatCost", "hp", "weakness", "resistance", "energyType",
        "basic", "stage1", "stage2", "ex", "megaEx", "tera", "aceSpec", "evolvesFrom",
        "n_attacks", "attacks",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in cards:
            writer.writerow({
                "cardId": c.cardId,
                "cardType": int(c.cardType),
                "retreatCost": c.retreatCost,
                "hp": c.hp,
                "weakness": int(c.weakness) if c.weakness is not None else "",
                "resistance": int(c.resistance) if c.resistance is not None else "",
                "energyType": int(c.energyType) if c.energyType is not None else -1,
                "basic": int(c.basic),
                "stage1": int(c.stage1),
                "stage2": int(c.stage2),
                "ex": int(c.ex),
                "megaEx": int(c.megaEx),
                "tera": int(c.tera),
                "aceSpec": int(c.aceSpec),
                "evolvesFrom": c.evolvesFrom or "",
                "n_attacks": len(c.attacks or []),
                "attacks": "|".join(str(a) for a in (c.attacks or [])),
            })
    print(f"exported {len(cards)} cards -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine-dir", required=True, help="A submission dir containing a cg/ package")
    parser.add_argument("--out", default="data/raw/EN_Card_Attrs.csv")
    args = parser.parse_args()
    export(args.engine_dir, args.out)
```

- [ ] **Step 2: Run it and diff against the old file's shared columns**

Run: `cp data/raw/EN_Card_Attrs.csv /tmp/EN_Card_Attrs_old.csv`
Run: `python3 src/export_card_attacks.py --engine-dir submissions/masamikobayashi_archaludon_cinderace --out data/raw/EN_Card_Attrs.csv`
Run: `python3 -c "
import csv
old = {r['cardId']: r for r in csv.DictReader(open('/tmp/EN_Card_Attrs_old.csv'))}
new = {r['cardId']: r for r in csv.DictReader(open('data/raw/EN_Card_Attrs.csv'))}
shared_cols = ['cardType','retreatCost','hp','basic','stage1','stage2','ex','megaEx','tera','n_attacks']
mismatches = 0
for cid, old_row in old.items():
    new_row = new.get(cid)
    if not new_row:
        continue
    for col in shared_cols:
        if old_row.get(col) != new_row.get(col):
            mismatches += 1
print(f'{len(old)} old cards, {len(new)} new cards, {mismatches} shared-column mismatches')
"`
Expected: `mismatches` is `0` — the regenerated file must agree with the old one on every column
it already had (a real check that the new script reproduces the existing, working data
correctly, not just that it runs).

- [ ] **Step 3: Add `attacks` to `load_card_attrs` in `src/features.py`**

```python
                "n_attacks": int(row.get("n_attacks", 0) or 0),
                "basic": int(row.get("basic", 0) or 0),
                "attacks": [int(a) for a in (row.get("attacks") or "").split("|") if a != ""],
```

- [ ] **Step 4: Compute `opt_energy_gap_before`/`opt_energy_gap_after` in `option_features`**

Add a helper above `option_features` in `src/features.py`:

```python
def _cheapest_attack_gap(pokemon_card_ids: list, energy_count: int, attack_data: dict, card_attrs: dict) -> int:
    """Given a Pokemon's card id and current energy count, return how many MORE energy
    attachments its cheapest known attack still needs (0 if already affordable)."""
    attrs = (card_attrs or {}).get(pokemon_card_ids, {})
    attack_ids = attrs.get("attacks") or []
    costs = [attack_data.get(aid, {}).get("energyCost") for aid in attack_ids]
    costs = [c for c in costs if c is not None]
    if not costs:
        return -1  # no known attacks (e.g. not evolved enough yet, or data gap) — unresolvable
    cheapest = min(costs)
    return max(0, cheapest - energy_count)
```

Then in `option_features`, inside the existing function body (after `target_card` is computed),
add the ATTACH-specific computation:

```python
    energy_gap_before = -1
    energy_gap_after = -1
    if option.get("type") == OPT_ATTACH and target:
        target_energy_count = len(target.get("energyCards") or [])
        energy_gap_before = _cheapest_attack_gap(target.get("id"), target_energy_count, attack_data, card_attrs)
        if energy_gap_before != -1:
            energy_gap_after = max(0, energy_gap_before - 1)
```

And add two keys to the returned dict:

```python
        "opt_energy_gap_before": energy_gap_before,
        "opt_energy_gap_after": energy_gap_after,
```

- [ ] **Step 5: Verify with a targeted check against real card data**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from features import load_card_attrs, load_attack_data, _cheapest_attack_gap
attrs = load_card_attrs()
attacks = load_attack_data()
# Pick any card with at least one known attack and print its cheapest cost.
for cid, a in attrs.items():
    if a.get('attacks'):
        gap0 = _cheapest_attack_gap(cid, 0, attacks, attrs)
        print(f'card {cid}: attacks={a[\"attacks\"]}, gap at 0 energy={gap0}')
        break
"
```
Expected: prints a real card ID with a non-negative `gap0` matching its cheapest attack's
`energyCost` from `EN_Attack_Data.csv` — spot-check that number by eye against
`data/raw/EN_Attack_Data.csv` for that specific attack ID.

- [ ] **Step 6: Copy the regenerated CSV into every submission dir that ships it**

```bash
cp data/raw/EN_Card_Attrs.csv submissions/il_agent_v3/EN_Card_Attrs.csv
```

- [ ] **Step 7: Commit**

```bash
git add src/export_card_attacks.py src/features.py
git commit -m "feat: add energy_gap_before/after ATTACH feature, backed by a new card->attack-IDs export script"
```

(`data/raw/EN_Card_Attrs.csv` itself is gitignored, per Global Constraints — only the generator
script and `features.py` changes are committed.)

---

### Task 6: Full retrain with all changes, offline Gate A

**Files:**
- No new files — this task runs the already-modified `src/train_il_model.py` against real data
  at scale and records the result.

**Interfaces:**
- Consumes: everything from Tasks 2-5 (leaderboard-joined, per-side-filtered data; ELO features
  and sample weights; deduped labels; energy_gap feature).
- Produces: `models/il_scorer_v3.pkl` (joblib bundle: `{"model", "feature_columns"}`, same shape
  as v2's — Task 7 adds the calibrated threshold on top of this).

- [ ] **Step 1: Regenerate the ELO-filtered day's data with the Task 2 per-side policy**

The existing `data/processed/il_records_2026-08-05.jsonl` (3.37GB) was produced by the *old*
per-episode filter and has no `actor_score`/`opp_score` fields — it must be regenerated, not
reused as-is.

Run: `python3 src/leaderboard.py --out data/raw/leaderboard.csv` (skip if Task 2 Step 3 already
did this within the last few hours — leaderboard scores don't need refreshing more than once per
retrain).

Run: `python3 src/episode_stream.py --day 2026-08-05 --out data/processed/il_records_2026-08-05_v3.jsonl`

Expected: prints `2026-08-05: K/N episodes kept (>=1 side score >= 950.0), 0 tripwire failures ->
...` — note the new `kept` count and compare it informally to whatever the original run reported
(it may be similar or lower now that only qualifying *sides'* records survive, not whole
episodes) — this is expected and fine, not a bug.

- [ ] **Step 2: Combine with the original 299-episode data**

The original `data/processed/il_records.jsonl` (228MB, 299 episodes, no leaderboard join,
`actor_score`/`opp_score` both `None` on every line — handled gracefully by Tasks 3/4's code)
stays valid as-is. Combine:

```bash
cat data/processed/il_records.jsonl data/processed/il_records_2026-08-05_v3.jsonl > data/processed/il_records_v3_combined.jsonl
wc -l data/processed/il_records_v3_combined.jsonl
```

- [ ] **Step 3: Train**

Run: `python3 src/train_il_model.py --records data/processed/il_records_v3_combined.jsonl --out models/il_scorer_v3.pkl`

This is the 3+GB run — expect it to take meaningfully longer than the `--max-records 5000` sanity
runs from earlier tasks. Let it finish; don't `--max-records` this one.

- [ ] **Step 4: Gate A — offline sanity check**

Read the printed `per-decision top-1 accuracy — train: X, test: Y` line.

**Bar: test accuracy ≥ 0.55 overall.** (The original IL rebuild plan's Gate A bar was "overall
≥60%, MAIN≥50%" after fixing the pairing/resolution bugs alone, achieving 60.1%/53.3% — this
task adds ELO weighting, dedup, and energy_gap on top of that already-fixed baseline, so
regressing below 55% would mean something in Tasks 2-5 broke rather than improved the pipeline.
If it lands below 0.55, don't proceed to Task 7 — bisect Tasks 2-5 by reverting one at a time and
retraining on a `--max-records` subsample to find which change regressed things.)

Per the Global Constraints, remember this number is a debugging signal, not the real gate — Task
7's `local_eval` pooled win rate is what actually decides whether to submit.

- [ ] **Step 5: No commit this step** (the model file is gitignored — nothing to commit; the
  code that produced it was already committed in Tasks 2-5).

---

### Task 7: Export, calibrate threshold, package as `il_agent_v3`, Gate B

**Files:**
- Modify: `src/export_pure_predictor.py` (carry a calibrated threshold into the JSON bundle)
- Create: `src/calibrate_threshold.py`
- Modify: `submissions/il_agent_v3/main.py` (read threshold from the bundle instead of a
  hardcoded constant)
- Modify: `submissions/il_agent_v3/` data files (replace with v3's model/CSVs)

**Interfaces:**
- Consumes: `models/il_scorer_v3.pkl` from Task 6.
- Produces: `models/il_scorer_v3_pure.json` with an added `"threshold": float` key (alongside
  the existing `"feature_columns"`, `"baseline"`, `"trees"`). `main.py` reads
  `_BUNDLE.get("threshold", 0.5)` instead of a module-level `_THRESHOLD = 0.5` constant.

- [ ] **Step 1: Write `src/calibrate_threshold.py`**

```python
"""Sweep the option-selection probability threshold on a held-out split, optimizing for
decision-level exact-set-match (predicted chosen set == actual chosen set) rather than top-1 —
this is what actually determines in-game behavior (main.py clips a thresholded set to
[minCount, maxCount], not just an argmax).

Usage:
    python src/calibrate_threshold.py --model models/il_scorer_v3.pkl --records data/processed/il_records_v3_combined.jsonl --out models/il_scorer_v3_threshold.txt
"""

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import build_dataset  # noqa: E402


def exact_match_rate(model, X, decision_ids, y, select_min_max, threshold):
    scores = model.predict_proba(X)[:, 1]
    correct, total = 0, 0
    for dec_id in np.unique(decision_ids):
        mask = decision_ids == dec_id
        dec_scores = scores[mask]
        dec_labels = y[mask]
        min_c, max_c = select_min_max[dec_id]
        ranked = np.argsort(-dec_scores)
        above = [i for i in ranked if dec_scores[i] > threshold]
        if len(above) < min_c:
            chosen = set(ranked[:min_c])
        elif len(above) > max_c:
            chosen = set(ranked[:max_c])
        else:
            chosen = set(above)
        actual = set(np.where(dec_labels == 1)[0])
        total += 1
        if chosen == actual:
            correct += 1
    return correct / total if total else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--records", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    # Safe: loading our own model artifact, trained locally by src/train_il_model.py in this
    # same pipeline — not an untrusted source. Same pattern already used in
    # src/export_pure_predictor.py. This script only ever runs on our own machine, never in the
    # Kaggle sandbox — the exported pure-JSON bundle (Task 7 Step 3-4) is what actually ships.
    bundle = joblib.load(args.model)
    model, feature_columns = bundle["model"], bundle["feature_columns"]

    rows, labels, decision_ids, _weights = build_dataset(args.records)
    X = pd.DataFrame(rows)[feature_columns]
    y = np.array(labels)
    groups = np.array(decision_ids)

    # Recover per-decision minCount/maxCount for the exact-set-match check.
    select_min_max = {}
    for row, dec_id in zip(rows, decision_ids):
        if dec_id not in select_min_max:
            select_min_max[dec_id] = (row["select_minCount"], row["select_maxCount"])

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)
    _, test_idx = next(splitter.split(X, y, groups))
    X_test, y_test, groups_test = X.iloc[test_idx], y[test_idx], groups[test_idx]

    best_threshold, best_rate = 0.5, -1.0
    for threshold in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]:
        rate = exact_match_rate(model, X_test, groups_test, y_test, select_min_max, threshold)
        print(f"threshold {threshold:.2f}: exact-set-match {rate:.3f}")
        if rate > best_rate:
            best_threshold, best_rate = threshold, rate

    print(f"best threshold: {best_threshold} (exact-set-match {best_rate:.3f})")
    Path(args.out).write_text(str(best_threshold))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `python3 src/calibrate_threshold.py --model models/il_scorer_v3.pkl --records data/processed/il_records_v3_combined.jsonl --out models/il_scorer_v3_threshold.txt`

Expected: a table of 9 threshold/exact-match-rate pairs, then a `best threshold: ...` line.
Sanity check: the best rate should be higher than whatever `0.5`'s own printed rate was in the
same table — if `0.5` already wins, that's a legitimate (if slightly disappointing) result, not
a bug; record whatever the sweep actually finds.

- [ ] **Step 3: Update `src/export_pure_predictor.py` to carry the threshold**

```python
def export_model(model_path: str, out_path: str, threshold: float = 0.5):
    import joblib

    bundle = joblib.load(model_path)
    model = bundle["model"]
    feature_columns = bundle["feature_columns"]

    trees = []
    for stage in model._predictors:
        tree = stage[0]
        nodes = []
        for node in tree.nodes:
            nodes.append(
                [
                    int(node["feature_idx"]),
                    float(node["num_threshold"]),
                    int(node["missing_go_to_left"]),
                    int(node["left"]),
                    int(node["right"]),
                    int(node["is_leaf"]),
                    float(node["value"]),
                ]
            )
        trees.append(nodes)

    baseline = float(model._baseline_prediction.reshape(-1)[0])

    payload = {
        "feature_columns": feature_columns,
        "baseline": baseline,
        "trees": trees,
        "threshold": threshold,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f)
    print(f"exported {len(trees)} trees, {sum(len(t) for t in trees)} nodes, threshold={threshold} -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="models/il_scorer_v2.pkl")
    parser.add_argument("--out", default="models/il_scorer_v2_pure.json")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    export_model(args.model, args.out, args.threshold)
```

- [ ] **Step 4: Export v3 with its calibrated threshold**

```bash
THRESHOLD=$(cat models/il_scorer_v3_threshold.txt)
python3 src/export_pure_predictor.py --model models/il_scorer_v3.pkl --out models/il_scorer_v3_pure.json --threshold "$THRESHOLD"
```

- [ ] **Step 5: Validate the pure-Python export still matches sklearn, same as v2's original validation**

```bash
python3 -c "
import sys, json
sys.path.insert(0, 'src')
import joblib, pandas as pd
from features import build_dataset
import pure_predictor

bundle_sk = joblib.load('models/il_scorer_v3.pkl')
model, cols = bundle_sk['model'], bundle_sk['feature_columns']
rows, labels, decision_ids, _ = build_dataset('data/processed/il_records.jsonl', None, None, None)
X = pd.DataFrame(rows)[cols].head(200)
sk_scores = model.predict_proba(X)[:, 1]

bundle_pure = pure_predictor.load('models/il_scorer_v3_pure.json')
feature_rows = X.values.tolist()
pure_scores = pure_predictor.predict_proba_batch(bundle_pure, feature_rows)

import numpy as np
diff = np.abs(np.array(sk_scores) - np.array(pure_scores))
print('max diff:', diff.max())
"
```
Expected: `max diff: 0.0` (or within float rounding, e.g. `< 1e-9`) — same validation bar v2 was
held to before it shipped. Do not proceed if this fails.

- [ ] **Step 6: Update `submissions/il_agent_v3/main.py` to read the threshold from the bundle**

Replace the module-level constant:

```python
_BUNDLE = pure_predictor.load(_find(os.path.join("models", "il_scorer_v3_pure.json")))
_FEATURE_COLUMNS = _BUNDLE["feature_columns"]
_CARD_DATA = il_features.load_card_data(_find("EN_Card_Data.csv"))
_ATTACK_DATA = il_features.load_attack_data(_find("EN_Attack_Data.csv"))
_CARD_ATTRS = il_features.load_card_attrs(_find("EN_Card_Attrs.csv"))
_THRESHOLD = _BUNDLE.get("threshold", 0.5)
```

(Delete the old hardcoded `_THRESHOLD = 0.5` line and its comment — the bundle is now the source
of truth.)

- [ ] **Step 7: Copy v3's artifacts into the submission directory**

```bash
mkdir -p submissions/il_agent_v3/models
cp models/il_scorer_v3_pure.json submissions/il_agent_v3/models/il_scorer_v3_pure.json
rm -f submissions/il_agent_v3/models/il_scorer_v2_pure.json
cp src/features.py submissions/il_agent_v3/il_features.py
cp data/raw/EN_Card_Attrs.csv submissions/il_agent_v3/EN_Card_Attrs.csv
```

(Double-check `EN_Card_Data.csv` and `EN_Attack_Data.csv` don't need refreshing — Task 5 didn't
touch either of those, only `EN_Card_Attrs.csv`.)

- [ ] **Step 8: Syntax check and smoke test**

Run: `python3 -m py_compile submissions/il_agent_v3/main.py`
Run: `python3 .claude/skills/run-battle/scripts/run_battle.py --candidate submissions/il_agent_v3 --opponent submissions/masamikobayashi_archaludon_cinderace --battles 6`
Expected: no exceptions.

- [ ] **Step 9: Gate B — local pooled win rate**

Run: `python3 src/local_eval.py --candidate submissions/il_agent_v3 --battles 20 --repeats 3 --save-losses /tmp/il_v3_losses`

**Bar: pooled win rate must clear both (a) `il_agent_v2`'s last measured real number (47.5%) with
the improvement outside the 95% CI's lower bound overlapping that figure, and (b) not regress
versus Task 1's guardrail-only checkpoint from Step 8 of Task 1.** If it clears this bar, proceed
to Task 8. If it doesn't, this is a real, informative result — per the Global Constraints, do not
spend a submission on it; instead use `--save-losses`'s output the same way the Dragapult ex
investigation did (trace 2-3 actual losses, classify by `Result.reason`, look for a concrete,
evidence-backed cause) before deciding whether another iteration is worth the remaining days.

- [ ] **Step 10: Commit**

```bash
git add src/export_pure_predictor.py src/calibrate_threshold.py
git commit -m "feat: calibrate il_agent_v3's selection threshold against exact-set-match, carry it in the exported bundle"
```

---

### Task 8: Submit and read the real ladder result, Gate C

**Files:** none — this is a process task (packaging, submitting, documenting), not a code task.

- [ ] **Step 1: Package the tar and validate required files**

```bash
cd submissions/il_agent_v3
tar -czf submission.tar.gz main.py deck.csv EN_Card_Data.csv EN_Attack_Data.csv EN_Card_Attrs.csv il_features.py models
cd -
python3 -c "
import tarfile
required = {'main.py', 'deck.csv'}
with tarfile.open('submissions/il_agent_v3/submission.tar.gz') as t:
    names = set(t.getnames())
missing = required - names
print('missing:', missing if missing else 'none')
"
```

(This agent doesn't need the `cg/` engine bundled the way the rule-based agents do — confirm by
checking whether `submissions/il_agent_v2/submission.tar.gz`, the last real IL submission,
included a `cg/` directory before assuming either way; match whatever that one actually did.)

- [ ] **Step 2: Extracted-tar smoke test with site-packages stripped (the exact check that would
  have caught the original v2 ERROR before it cost a submission)**

```bash
rm -rf /tmp/il_v3_pkg && mkdir -p /tmp/il_v3_pkg
tar -xzf submissions/il_agent_v3/submission.tar.gz -C /tmp/il_v3_pkg
python3 -c "
import sys
sys.path = [p for p in sys.path if 'site-packages' not in p]
sys.path.insert(0, '/tmp/il_v3_pkg')
import main
print('agent callable:', callable(main.agent))
"
```
Expected: `agent callable: True`, no `ImportError` for numpy/pandas/sklearn/joblib.

- [ ] **Step 3: Confirm submission quota before spending one**

Run: `kaggle competitions submissions -c pokemon-tcg-ai-battle --csv | head -3`
Check today's UTC-day usage against the 5/day cap (remember: resets at UTC midnight, not local
date — check `date -u`, not `date`).

- [ ] **Step 4: Get explicit human confirmation before submitting**

Per Global Constraints, this plan does not authorize an autonomous Kaggle submission. Summarize
Task 7's Gate B numbers (pooled win rate, CI, comparison to v2's 47.5%) and ask before running
`kaggle competitions submit`.

- [ ] **Step 5: Submit (once confirmed) and log it**

```bash
kaggle competitions submit -c pokemon-tcg-ai-battle -f submissions/il_agent_v3/submission.tar.gz -m "<describe the guardrail + ELO-conditioning + dedup + energy_gap changes and the Gate B local_eval numbers here>"
```

Update `notebooks/kaggle-research/10-day-plan.md`'s submission log table with the new ref,
description, and status, matching its existing format (see the 2026-08-08 Dragapult entry for
the exact style to follow).

- [ ] **Step 6: Gate C — wait for 2 real readings, ≥24h apart, before deciding anything**

Compare against hardened Archaludon's real range (711-811, settled ~750-775) and the previous IL
attempt's real score (523-531). Document the outcome in
`notebooks/kaggle-research/baseline-comparison.md` (a new dated section, following the existing
style of the Dragapult and Archaludon-hardening sections) regardless of which way it goes —
including a clear-eyed "this didn't work, here's the evidence" writeup if the real score doesn't
improve, matching this project's established discipline of documenting negative results with the
same rigor as positive ones.

- [ ] **Step 7: Commit and push the documentation update**

```bash
bash .claude/skills/secrets-and-data-guard/scripts/scan.sh
git add notebooks/kaggle-research/10-day-plan.md notebooks/kaggle-research/baseline-comparison.md
git commit -m "docs: log il_agent_v3 submission and real-score outcome"
git push
```

---

## Optional stretch task (only if every gate above passed with days to spare)

**Filtered self-imitation** — run `il_agent_v3` in self-play against itself and the rule-based
roster via `local_eval.py` (or a small new script reusing `cg.game.battle_start`/`battle_select`
directly), keep only the (observation, action) pairs from games it *won*, append them to the
training set at a low `sample_weight` (e.g. 0.3, well below any real-player-derived weight),
retrain once, and keep the result only if `local_eval` pooled win rate improves outside the
current model's Wilson interval. No search, no value network, no MCTS — purely more supervised
training data generated by the current best policy, filtered by outcome. If this doesn't clearly
help within one iteration, stop — this is explicitly a stretch task, not a required gate.
