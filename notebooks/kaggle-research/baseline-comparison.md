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

*Footnote: this table was computed against the pre-`il_agent_v2b` 4-agent roster (random
baseline + these 3 submissions only). The default roster is now 5 agents (`il_agent_v2b` added),
so these exact numbers are not reproducible against current `src/local_eval.py` runs.*

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

## Rule-based hardening pass (2026-08-07, done in a parallel worktree while waiting on the IL reading)

Resolves recommendation #2 above. Went through every correctness-relevant item flagged in
`discussion-intel-report.md` against `submissions/masamikobayashi_archaludon_cinderace/main.py`
directly — verifying against the real engine rather than assuming a gap exists just because it
was the most-repeated advice in the wider research (that advice came largely from TomBombadyl's
own, differently-tuned agent).

**Checked and confirmed already safe — no fix needed:**
- `#730707` (broad `except` returning the deck list mid-game): not present. The exception path
  only ever falls back to a random legal sample, never the deck-submission response.
- Per-option scoring already isolates failures — a single option's scoring exception degrades
  that option to a very low score rather than crashing the whole decision.
- Bench-empty handling is proactive, not reactive: playing any available basic Pokémon is
  unconditionally high-priority (18000) regardless of current bench state. Ultra Ball's lower
  priority specifically when the bench is empty is deliberate author tuning (search doesn't fix
  emptiness *this turn* the way playing a card already in hand does), not an oversight.
- Mandatory promote after a KO (`TO_ACTIVE`/`SWITCH`): every option scores ≥1000 in that
  context, so the agent structurally never declines when forced to choose a new active.
- `#716241` (Rare Candy consumed without evolving after Evolution Jammer): this deck has zero
  Rare Candy — doesn't apply.
- `#708586`'s report that Setup sometimes forces benching a spare Basic with no decline option:
  **tested empirically against the real `cg` engine across 15 games** — `SETUP_BENCH_POKEMON`'s
  `minCount` was 0 every single time observed. Doesn't reproduce here; declining is always legal
  in what we could observe.

**One real, confirmed gap found and fixed:** the top-level exception fallback did
`random.sample(options, obs.select.maxCount)` unclipped — if `maxCount` ever exceeded the actual
number of legal options, that call would itself raise, uncaught, since it's already inside the
last-resort `except` block. Fixed to clip to `[minCount, min(maxCount, n_options)]`. Verified
10/10 still passes locally after the change; the fix is live in
`submissions/masamikobayashi_archaludon_cinderace/main.py` (not committed to git — `submissions/`
is gitignored by design, third-party-derived agent code).

**Not actionable**: `#733265` (simulator allegedly swapping decks between players) — engine-side,
unconfirmed by the host as of the discussion pull, nothing to code defensively against from our
side.

**Real-world validation (2026-08-07, ref `55327510`):** submitted the hardened version — scored
**771.6**, up from the unhardened 643.1. A **+128.5** jump from one small robustness fix is a
strong signal that `maxCount > len(options)` was genuinely occurring in real games and silently
losing them via the previously-unguarded exception fallback. This is the clearest evidence all
session that a targeted code fix, not archetype or deck choice, can move the real score
substantially — worth remembering before assuming further gains require a bigger rebuild.

## Matchup-logic audit (2026-08-07, second pass)

Follow-up to the hardening pass above, this time targeting the matchup-specific branches
(Crustle/Alakazam/Hop) rather than the general-purpose checklist items — these are the densest,
least-tested code in `submissions/masamikobayashi_archaludon_cinderace/main.py` (per-opponent
override blocks with layered conditions, easy to get subtly wrong), audited with the same
real-engine-verification rigor: every claim checked against the real `cg` engine's card DB
and dataclass source, not assumed from variable names or comments.

**Confirmed and fixed:** the `detect_matchup`/`all_my_pokemon` `None`-active crash. Per the
engine's own `PlayerState.active` field comment (`list[Pokemon | None]  # ... None if the card is
facedown`), an opponent's (or, more defensively, our own) active Pokémon can legitimately be
`None` when face-down. `detect_matchup` computed `opp.active + opp.bench` without guarding this
case, while sibling functions elsewhere in the file already did — an inconsistency that turned a
documented, reachable engine state into an uncaught `TypeError: unsupported operand type(s) for
+: 'NoneType' and 'list'`. Because this crash sits inside the per-option scoring path, and that
path's own exception isolation degrades a *single* option's score to a very low fallback rather
than crashing the whole decision, a face-down active silently forced every option in that
decision down to the -999999 floor — turning a normally-reasoned choice into an effectively random
one for that turn. Fixed by guarding both functions with `(x or [])` before concatenation;
reproduced the crash synthetically first, confirmed the fix eliminates it, then re-ran a 10-battle
regression (10/10 wins, no errors) to confirm no behavior change on the non-crashing path.

**Checked and confirmed already safe** (no fix needed):
- **Crustle override branch ordering.** Verified against real card data pulled from the engine's
  own `all_card_data()` (Duraludon's actual attack list `[Hammer In, Raging Hammer]` — it does not
  know Metal Defender; Archaludon ex's attack list `[Metal Defender]`; Crustle's "Mysterious Rock
  Inn" ability, which blocks all damage from the opponent's `ex` Pokémon specifically; Spiky
  Energy's fixed 20-HP recoil to whoever damages its holder). The one apparent case of an earlier,
  broader condition ("full HP Duraludon waits out Spiky") shadowing a later, more specific one
  ("Crustle: Raging Hammer") is real and reproduces, but is not a bug: because Metal Defender is
  never reachable while Duraludon is active, the broad condition can, by construction, only ever
  intercept Raging Hammer — a deliberate, game-rule-consistent precedence (don't spend your only
  clean attacker's HP for one turn of chip damage while at full HP), not an accidental catch-all.
- **The Alakazam `enriching_seen` card-ID check.** Card 13, checked directly against the engine's
  card DB, is confirmed to be Enriching Energy (ACE SPEC, "draw 4 cards" on attach) — exactly the
  one-time hand-size burst the variable name describes. The heuristic's `None`/empty-bench
  handling was also traced end-to-end: `bench` is never `None`-padded per the engine's own type
  contract (`list[Pokemon]`, no facedown case, unlike `active`), and the one possible `None`
  (a face-down active) is filtered out by an `if p` guard before any attribute access. ID and
  guard logic both check out.
- **The Hop/Snorlax `active.hp > 220` threshold.** Confirmed `hp` is current, damage-reduced HP —
  not max HP — per the engine's own dataclass comment ("Current HP.") and corroborated by this
  file's own `damage_on` helper (`maxHp - hp`, used additively everywhere it appears, never as a
  "derive current HP" step, which would be redundant if `.hp` were already current). Five other
  bare `.hp > threshold` comparisons elsewhere in the file use the identical idiom, so this branch
  is consistent with the file's own established (and correct) convention, not an outlier.

**Deferred, out of this audit's scope:** the `rh_dmg` dead-variable observation from the Crustle
audit — in the Raging Hammer branch, `rh_dmg = 80 + damage_on(active_pokemon(obs)) // 10 * 10` is
computed but never used; the actual return is `max(score, 200)`, a hardcoded floor, not
`max(score, rh_dmg)`. Plausibly the intent was to scale the floor with accumulated damage (mirroring
`best_attack_damage`'s identical formula), but this doesn't change branch precedence/shadowing —
the thing this audit was scoped to check — so it was left untouched. Worth a follow-up look, not a
fix bundled into this round.

**Local validation (2026-08-07, post-fix, pre-submission):**

```
$ python3 .claude/skills/run-battle/scripts/run_battle.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 20
battle 0: first=candidate winner=candidate
battle 1: first=opponent winner=candidate
battle 2: first=candidate winner=candidate
battle 3: first=opponent winner=candidate
battle 4: first=candidate winner=candidate
battle 5: first=opponent winner=candidate
battle 6: first=candidate winner=candidate
battle 7: first=opponent winner=candidate
battle 8: first=candidate winner=candidate
battle 9: first=opponent winner=candidate
battle 10: first=candidate winner=candidate
battle 11: first=opponent winner=candidate
battle 12: first=candidate winner=opponent
battle 13: first=opponent winner=candidate
battle 14: first=candidate winner=candidate
battle 15: first=opponent winner=candidate
battle 16: first=candidate winner=candidate
battle 17: first=opponent winner=candidate
battle 18: first=candidate winner=candidate
battle 19: first=opponent winner=candidate

candidate wins: 19/20 (95.0%)
opponent  wins: 1/20 (5.0%)
```

```
$ python3 src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace --battles 20
opponent                                   wins  games  errors    win%           95% CI
sample_submission                            19     20       0   95.0% [ 76.4,  99.1]
kiyota_mega_lucario_ex                       15     20       0   75.0% [ 53.1,  88.8]
soutasakurai_libraryout_crustle               6     20       0   30.0% [ 14.5,  51.9]

pooled: 40/60 (66.7%) 95% CI [54.1, 77.3]
```

Zero errors across both harnesses (80 games total) — consistent with the fix being a clean,
non-disruptive guard rather than a behavior change on any previously-working path. Per this
doc's own earlier calibration note, pooled local win rate is a coarse "not obviously broken"
filter, not a ladder-μ predictor — this run's job was to confirm the fix didn't regress anything
locally, not to forecast the real score.

## Dragapult ex `no_active` loss investigation and fix (2026-08-08)

`kiyota_dragapult_ex` (raw, submitted as `55335494`, real score settled **703.5**) was showing
`no_active` (`Result.reason == 3`) losses in local eval, roughly 15-25% of losses vs Archaludon
and Lucario. User confirmed building a "bench guard" to target this. Before writing anything,
traced the actual replay JSON for the loss pattern (`local_eval.py --save-losses`,
`cg.game.visualize_data()` merged with per-step obs/action) rather than assuming the fix from the
aggregate stat alone — this session's standing discipline.

**First correction (premise didn't survive tracing):** the first three sampled `no_active`
losses (2 vs Archaludon, 1 vs Lucario) each showed the bench genuinely had **zero legal Basic
Pokémon to place** at the fatal decision — Drakloak (a Stage 1) isn't a Basic and can't be
benched directly; the deck only carries 6 real Basics in 60 cards (Dreepy×4, Budew×2). A
"prioritize benching when possible" guard would not have prevented any of those three losses —
there was nothing legal to bench. This is genuine deck-thinness risk, not a decision bug.

**Second pass, real bug found:** re-examining one trace (`…archaludon_cinderace_r0_battle3`,
step 5) at the *option level* (not just hand/bench snapshots) showed the agent had **two ignored
legal alternatives** to the action it actually took (attaching energy to its lone active): (a)
play `Fezandipiti_ex` — a Basic Pokémon sitting in hand — onto the empty bench, or (b) dig with
`Ultra_Ball`. It attached energy instead. Root cause in `main_option_proc`'s `hand_score`
closure: every other non-Dreepy-line Basic (`Budew`, `Meowth_ex`, `Latias_ex`) has an explicit
fallback branch giving it a positive score even outside its special-case conditions (e.g. Budew:
`elif state.turn >= 2: score = 30000`) — but `Fezandipiti_ex`'s branch had no such fallback:

```python
elif id == Fezandipiti_ex:
    if pre_ko:
        score = 50000
    elif prize_diff <= -2:
        score = 5
    elif len(op_state.prize) == 1:
        score = UNNECESSARY
    # falls through to score = 0 otherwise
```

And the `OptionType.PLAY` handler gates strictly on that score: `if card_score > 0: score =
53000 else: score = -1` — so whenever none of the three special conditions held (the common
case, including exactly the empty-bench emergency observed), `Fezandipiti_ex` was **vetoed from
ever being played**, regardless of board state. Fix (`submissions/kiyota_dragapult_ex/main.py`,
in the `hand_score` closure):

```python
elif id == Fezandipiti_ex:
    if pre_ko:
        score = 50000
    elif prize_diff <= -2:
        score = 5
    elif len(op_state.prize) == 1:
        score = UNNECESSARY
    elif len(my_state.bench) == 0:
        score = 25000
```

`my_state.bench` is the player's own bench list — never contains `None` (own-side state has no
hidden information, confirmed by the existing code's unguarded `for card in my_state.bench:`
loop with no None-check, unlike the opponent-facing `active` loop which does guard against it).

**Validated before submitting** — `local_eval.py --battles 20 --repeats 3 --save-losses`,
compared against the pre-fix baseline:

| | pre-fix | post-fix |
|---|---|---|
| pooled win rate | 158/225 (70.2%) [63.9, 75.8] | 214/300 (71.3%) [66.0, 76.2] |
| vs Archaludon | 35.6% | 35.0% [24.2, 47.6] |
| vs Archaludon, `no_active` share of losses | ~15-25%* | 3/39 losses = **7.7%** |
| vs Lucario, `no_active` share of losses | ~15-25%* | 1/24 losses = **4.2%** |

*(aggregate estimate from the original loss-reason classification, not matchup-specific)*

Pooled and per-matchup win rates are statistically unchanged (CIs heavily overlap) — this is the
expected signature of a clean, narrowly-scoped fix: it doesn't touch any other decision path, so
nothing else should move. The `no_active` share dropped ~3-4x in the two matchups where it
mattered. Residual `no_active` losses remain (the genuine no-basic-in-hand deck-thinness cases
from the first tracing pass) — this fix does not and cannot eliminate those.

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
