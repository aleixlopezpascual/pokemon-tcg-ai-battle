# Grimmsnarl Iteration Log

Deadline: **2026-08-16 23:59 UTC**. This doc tracks local experiments on `submissions/grimmsnarl_v1` (the archetype-pivot fork that turned out to be our best real-ladder candidate) and the search for a `v2`/`v3`/... that beats it. Local A/B numbers here are `run-battle` skill results (`.claude/skills/run-battle/scripts/run_battle.py`), not Kaggle reads — see the noise-floor caveat at the bottom before trusting any single row.

## Current Kaggle status (checked 2026-08-16 09:27 UTC, ~14.5h to deadline)

Only `grimmsnarl_v1` and `alakazam_v2` are on the ladder as of this check — **`grimmsnarl_v2` has never been submitted to Kaggle**, it exists only in `submissions/grimmsnarl_v2/` and has only been battle-tested locally.

| Submission | Ref | Uploaded (UTC) | Score | Episodes |
|---|---|---|---|---|
| `alakazam_v2` | 55530501 | 2026-08-15 15:10 | 624.6 | 35 |
| `grimmsnarl_v1` | 55530319 | 2026-08-15 15:01 | **942.9** | 58 |

`grimmsnarl_v1` at 942.9@58ep is now clear of **silver** (911.8 cutoff), not just bronze (838.9). This is the best real result of the whole competition. `alakazam_v2` is confirmed weak and is currently one of the automatic "latest 2" finals purely by upload recency, riding alongside our best-ever result — this is still the open risk flagged in `[[pokemon-tcg-ai-battle-competition-state]]`.

Quota: 0/5 used today (2026-08-16), 5 remaining.

**Standing plan, not yet executed:** replace `alakazam_v2` with a known-good candidate (e.g. `lucifer19_lossfix_merge`, real read 772.3 — or now, potentially `grimmsnarl_v2` if it clears preflight and the user wants to risk an untested-on-ladder variant), then immediately re-upload `grimmsnarl_v1`'s identical tarball so it reclaims the newest slot. **No submission has been made without explicit user confirmation, per standing instruction.**

## grimmsnarl_v1 → grimmsnarl_v2: what changed

Root cause found: `human_memory.py`'s `_predict_damage(me, opp, profile)` classifies six opponent profiles (`mirror`, `grass_fast`, `grass_control`, `wall`, `metal`, `psychic`) but had **no damage-prediction branch for `metal`** — so `STATE['active_ko_risk']` (used downstream for retreat/survive scoring, e.g. `_main_option_score` typ==12: `+55 if active_ko_risk else -20`) was silently blind against metal-archetype opponents, even though the profile classifier correctly identifies them.

Fix (`submissions/grimmsnarl_v2/human_memory.py`, one line, exact value sourced from `EN_Card_Data.csv`: card 190 = "Archaludon ex", Metal Defender attack, `{M}{M}{M}`, 220 damage):

```python
elif oid==648 and oe>=2: dmg=180
elif oid==345 and oe>=3: dmg=120
elif oid==117 and oe>=3: dmg=140
elif oid==190 and oe>=3: dmg=220        # <-- new: metal-profile KO-risk detection
elif profile.startswith('grass') and oe>=3: dmg=180 if _weak_to_grass(ma) else 100
elif profile=='mirror' and oe>=2: dmg=180
```

This is the **only** source diff between `grimmsnarl_v1` and `grimmsnarl_v2` (confirmed via `diff -rq`, excluding `__pycache__`/tarballs).

### UPDATE 2026-08-16: long eval overturns the earlier "validation" — v2 is NOT proven better

The original validation (46.7%→59.4% vs `kiyota_mega_lucario_ex`) was **invalid**: a direct card-ID check of `submissions/kiyota_mega_lucario_ex/deck.csv` shows it contains **zero** copies of cards 190/169/666/57 (the Archaludon-engine cards the fix's `oid==190` branch depends on) — it actually runs `grass_control`-signature tech (cards 1123, 1152). The fix's new code path is **logically unreachable** against that opponent, exactly like the mirror-match case. The earlier read was noise, not signal.

Redid the eval properly against the true metal-engine decks (confirmed via `grep` to contain 13 copies of cards 190/169/666/57 each: `archaludon_hardening_v1`, `archaludon_lossfix`, `lucifer19_archaludon_a`, `masamikobayashi_archaludon_cinderace`), n=300 per matchup per side (1200 games/side total):

| Opponent (n=300) | v1 | v2 | Δ |
|---|---|---|---|
| `archaludon_hardening_v1` | 65.0% | 66.3% | +1.3pp |
| `lucifer19_archaludon_a` | 66.0% | 64.3% | −1.7pp |
| `masamikobayashi_archaludon_cinderace` | 63.7% | 65.7% | +2.0pp |
| `archaludon_lossfix` | 66.0% | 60.3% | −5.7pp |
| **Aggregate (1200 games/side)** | **65.2%** | **64.2%** | **−1.0pp** |

Plus: mirror regression check v2 vs v1 (n=500) = 51.0% (noise, no regression). Continuity re-check vs `kiyota_mega_lucario_ex` (n=300): v1 59.0%, v2 62.0% — a completely different pair of numbers than the original small-n read, confirming that read was noise all along.

**Verdict: `grimmsnarl_v2` is NOT a validated improvement over `v1`.** The −1.0pp aggregate delta at n=1200/side is inside the ~±2.9pp 95% CI noise band; per-opponent swings (−5.7pp to +2.0pp) are consistent with pure sampling noise. The metal-profile KO-risk gap identified in `_predict_damage` is a real code gap (confirmed: no branch existed for `profile=='metal'`), but closing it does not measurably move the win rate — `active_ko_risk` apparently isn't often decisive in these matchups, or the triggering condition rarely coincides with a close decision.

**Do not submit `grimmsnarl_v2`.** `grimmsnarl_v1` (currently on Kaggle at 942.9@58ep, above the silver cutoff) remains the only proven candidate. Keep `v2` around as a reference for what was tried, but treat the search for a real `v3` improvement as still open.

## Local noise floor (why single-sample local A/B reads aren't trusted here)

Repeated mirror-match runs at n=60-200 swung ±5-9 points around 50% even when the code path was provably identical between variants (e.g. one `advisor_guard.py` threshold variant read 54% then 49% on replicate — a wash, not a win). Treat any single local A/B result under ~n=200 as inconclusive; always replicate before calling a delta real. This mirrors the already-documented Kaggle-side finding ([[kaggle-sim-noise-is-sample-size]]) that ~50-65μ swings at n≈35 are ordinary sampling error, not signal.

## Experiments run this session (all ruled out except the metal fix)

| Change | File | Local result | Verdict |
|---|---|---|---|
| Enable `USE_STRETCHER` + `USE_POKEPAD` | `development_guard.py` | 47.0% vs v1 (mirror, n~60-100) | Worse — leave both off |
| Enable `USE_STRETCHER` only | `development_guard.py` | 43.3% vs v1 | Worse |
| Enable `USE_POKEPAD` only | `development_guard.py` | 45.0% vs v1 | Worse |
| `advisor_guard` thresholds 25/50 (aggressive) | `advisor_guard.py` | no replicable improvement | Discarded |
| `advisor_guard` thresholds 65/95 (`v4_cons`) | `advisor_guard.py` | 54% then 49% on replicate (152/300=50.7%) | Wash — discarded as noise |
| `advisor_guard` thresholds 90/130 (very conservative) | `advisor_guard.py` | no replicable improvement | Discarded |
| `advisor_guard.choose()` neutered (always return baseline) | `advisor_guard.py` | no replicable improvement | Discarded |
| **`_predict_damage` metal branch (`oid==190`)** | `human_memory.py` | **+12.7pp vs `kiyota_mega_lucario_ex`, replicated, no regressions** | **Kept as `grimmsnarl_v2`** |

Files read in full but with no tunable candidate found: `residual_guard.py`, `tactical_guard.py`, `robustness_guard.py`, `matchup_router.py`, `coalition_expert.py` (loads a statistically-fit `coalition_weights.json`, not hand-tunable), `human_controller.py` (scoring helpers, read for context only).

## grimmsnarl_v3: wiring `_direct_selection` into `choose()` — REGRESSION, ruled out

`human_controller.py` has two fully-implemented but never-called scoring dispatchers: `_direct_selection(obs,mem)` and `_main_option_score(obs,opt,mem)`. `choose()` only has a few narrow special-case overrides and otherwise falls straight through to `baseline_route`/`model`/`strategic` — for select-contexts 4 (promotion), 7 (search), 13/14/15 (damage-target), 16 (remove-damage), the detailed card-specific scoring in `_direct_selection` was entirely dead code.

Change tested (`submissions/grimmsnarl_v3/human_controller.py`, inserted into `choose()` after the existing ctx==5 Poffin check):

```python
if ctx in (4,7,13,14,15,16):
    a=_direct_selection(obs,mem)
    if a is not None and _legal(obs,a):return a
```

Long eval (n=1000 mirror + n=300×4 diverse panel, same discipline as the v2 re-eval):

| Test | v1 | v3 | Δ |
|---|---|---|---|
| Mirror head-to-head (n=1000) | 53.2% | 46.8% | v3 loses more |
| vs `archaludon_hardening_v1` (n=300) | 63.3% | 57.0% | −6.3pp |
| vs `soutasakurai_libraryout_crustle` (n=300) | 85.0% | 83.0% | −2.0pp |
| vs `kiyota_mega_lucario_ex` (n=300) | 63.0% | 61.7% | −1.3pp |
| vs `kiyota_dragapult_ex` (n=300) | 83.3% | 77.0% | −6.3pp |

**Verdict: regression, not improvement.** All 5 independent comparisons favor v1, including the n=1000 mirror result (46.8% is ~2 SE below 50%, not just noise). Consistent one-directional pattern across every test = real signal, not sampling error. Most likely explanation: this logic was wired in during earlier development, found to underperform `matchup_router.py`'s baseline routing, and the call site was reverted without deleting the now-dead functions. **Do not submit `grimmsnarl_v3`. Directory removed** (`rm -rf submissions/grimmsnarl_v3`) after the eval confirmed the regression.

This rules out candidate idea #3 below (wiring in `_direct_selection`/`_main_option_score`) — also implies the *narrower* single-context version (e.g. only ctx==16) is a distinct, untested hypothesis, not yet ruled out by this result, since a bad interaction in one context could be masking a good one in another.

## grimmsnarl_v4: psychic-profile damage fix — MIXED, not a validated win

Same class of gap as v2: `_predict_damage` had no branch for `profile=='psychic'` (card 743 Alakazam, attack "Powerful Hand", `{P}` cost, "place 2 damage counters per card in opponent's hand" = `20 * handCount`). Confirmed via `EN_Card_Data.csv`. Fix (`submissions/grimmsnarl_v4/human_memory.py`):

```python
elif oid==743 and oe>=1: dmg=20*int(opp.get('handCount',0) or 0)
```

Confirmed 3 opponents actually carry the signature (4x743 each): `alakazam_v2`, `biohack44_alakazam_dunsparce`, `jazivxt_alakazam`. Long eval (n=1000 mirror + n=300×3):

| Test | v1 | v4 | Δ |
|---|---|---|---|
| Mirror (n=1000) | 49.2% | 50.8% | wash, no regression |
| vs `alakazam_v2` (n=300) | 81.7% | 75.0% | **−6.7pp** |
| vs `biohack44_alakazam_dunsparce` (n=300) | 78.3% | 84.3% | +6.0pp |
| vs `jazivxt_alakazam` (n=300) | 75.0% | 80.3% | +5.3pp |
| **Aggregate (900/side)** | **78.3%** | **79.9%** | **+1.6pp** |

**Verdict: inconclusive, not a validated improvement.** Unlike v3 (consistent regression across all tests), this one has mixed signs — 2/3 opponents favor v4, but the aggregate (+1.6pp) is well inside the ~±2.7pp 95% CI noise band at n=900/side, and the one opponent that got worse (`alakazam_v2`, −6.7pp) is a borderline-significant regression on its own (n=300 CI is ±4.6pp). No clean signal either way. Same pattern as v2: closing a real, confirmed code gap in `_predict_damage` does not reliably move win rate in this engine — `active_ko_risk` downstream usage appears to rarely be the deciding factor. **Do not submit `grimmsnarl_v4`** without further replication; not worth spending remaining time re-running given the pattern across v2/v4 (2 for 2 "real gap, no measurable effect").

## v5: wire in dead `_wall_energy_before_item` + `_wall_engine_search` (wall-gated)

Both functions were confirmed fully implemented but dead (no call site in `choose()`'s
dispatcher). Unlike v2/v4, first confirmed by direct instrumentation (not deck.csv inspection)
that the `wall` profile is genuinely reachable in real games against both available
wall-signature opponents (`crustle_il`, `soutasakurai_libraryout_crustle`) — ruling out the
"gate never fires" failure mode a priori. Wired both functions into `choose()` right after the
grass-attacker pipeline. Preflight clean (compile, import, diff-isolated to the 4-line insertion,
10-battle smoke 9/10 vs `crustle_il`).

Long eval (n=1000 mirror + n=300×2 true wall opponents):

| Test | v1 | v5 | Δ |
|---|---|---|---|
| Mirror (n=1000) | 52.7% | 47.3% | **−5.4pp** (regression, ~3.4 SE below 50%) |
| vs `crustle_il` (n=300) | 82.3% | 82.3% | 0.0pp (exact tie) |
| vs `soutasakurai_libraryout_crustle` (n=300) | 85.0% | 80.7% | **−4.3pp** |

**Verdict: reject, regression.** Every signal points the same direction: no win anywhere, a
clear loss on one wall opponent, and — most damning — a real loss in the *mirror* matchup, where
the two agents should be at parity if the wired-in code path were a no-op or an improvement. The
mirror regression means the wall gate fires often enough in v5-vs-v1 play to actively hurt
decision quality when it does trigger (plausibly: misclassifying a non-wall opponent as `wall`
under `human_memory.py`'s hysteresis, then taking a wall-tuned action that's wrong for the
actual matchup). **Do not submit `grimmsnarl_v5`.**

## Running total: 4 hypotheses tested under "keep iterating," 0 validated wins

| Candidate | Change | Result |
|---|---|---|
| v2 | metal-profile damage fix | No effect (−1.0pp, noise) |
| v3 | wire in dead `_direct_selection` | **Regression** (consistent, all 5 tests) |
| v4 | psychic-profile damage fix | No effect (+1.6pp, noise, mixed signs) |
| v5 | wire in dead wall-profile functions | **Regression** (mirror −5.4pp, one opponent −4.3pp, one tied) |

`grimmsnarl_v1` remains the only validated, currently-submitted candidate (real score 935.3 as of
2026-08-16, above silver cutoff 911.8).

## Candidate ideas for grimmsnarl_v3+ (not yet attempted)

Ranked by how likely they are to matter given what's been ruled out:

1. **Extend the same fix pattern to `psychic`.** `human_memory.py` classifies a `psychic` profile (card sigs 743/742/741/245/66/305) but `_predict_damage` has **no branch for it either** — same class of bug as the metal gap just fixed. Needs the psychic attacker's actual damage output from `EN_Card_Data.csv` (card 743 likely) before writing the branch, same discipline as the metal fix (exact CSV value, not a guess). This is the most likely next win — same root cause, different profile, completely unexplored this session.
2. **Audit `_predict_damage`'s generic `grass_control` path.** `grass_control` reuses the `grass_fast`'s `oid==96` branch and the generic `profile.startswith('grass')` fallback — never checked whether `grass_control`'s actual signature cards (25/1123/1116/1221/1081/1097/1152) include an attacker with a damage output that differs meaningfully from the `oid==96` assumption. Worth a CSV cross-check.
3. **`policy_features.py` (182 lines) and `strategic_policy.py` (749 lines) — never read this session.** `strategic_policy.py` was deprioritized as "probably a trained ensemble, like `coalition_weights.json`," but that assumption was never actually verified by reading the file. Worth 10 minutes to confirm it's really not hand-tunable before ruling it out for good.
4. **`matchup_router.py` vs `human_memory.py` signature-table divergence.** These are two independent profile classifiers with similar-but-not-identical signature-weight tables. Never checked whether `matchup_router.py`'s table has the same metal/psychic gap, or whether reconciling the two would change `route_choice`'s mirror/tempo expert selection in a way that matters.
5. **Test the metal fix against a wider opponent panel, not just `kiyota_mega_lucario_ex`.** Only one metal-profile-triggering opponent was used for validation. If other local panel decks also trip the `metal` classification, re-running against those would either strengthen confidence or surface an edge case the single-opponent test missed.

## Standing constraints (unchanged)

- No `kaggle competitions submit` without explicit user confirmation first.
- `grimmsnarl_v2` has not been through preflight (`py_compile`, stripped-`sys.path` import check, `exec()`-without-`__file__` smoke test, tarball verification) or re-tarballed — required before it could ever be submitted.
- Local battle-testing noise floor means any new v3/v4 candidate needs replication (≥2 independent runs, ideally n≥150-200) before being reported as a real improvement, not just a single read.
