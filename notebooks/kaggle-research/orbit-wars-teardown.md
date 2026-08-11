# Orbit Wars top-3 teardown — what transfers to PTCG AI Battle

Mined the top-3 writeups from a different Kaggle simulation competition, **Orbit Wars**
(topic IDs `724268` 1st, `723728` 2nd, `723820` 3rd, slug `orbit-wars`), retrieved via
`kaggle competitions topic-messages <slug> <topic_id>` — the Discussion/writeup pages are JS
SPAs and `WebFetch` returns only the page title, same access pattern already documented for
this competition's own Discussion tab in `CLAUDE.md`.

Context at the time (2026-08-10): our best settled reading was ~687-811 μ (Archaludon
ex/Cinderace) against a live ladder top of 1205.7 — a ~400 μ gap, against a measured noise
floor of 24-63 μ between settled readings of byte-identical tarballs. So the gap is real and
structural, and no one-line heuristic tweak was going to close it; anything shipped from that
teardown had to be worth ≥100 μ in expectation or it would be unmeasurable.

## 1. The three solutions at a glance

| | 1st — Isaiah Pressman | 2nd — simjeg | 3rd — "Ab in den Orbit" |
|---|---|---|---|
| Approach | Pure self-play RL, no IL | IL → RL-finetune → **from-scratch RL** | Pure self-play RL, no IL |
| Algorithm | PPO (chose over IMPALA for scaling simplicity) | PPO via PufferLib | PPO + GAE + **PFSP** |
| Model | 38-block transformer, d=768, 16 heads, **200M params** | 1D-CNN encoder → ModernBERT-XXS (7 layers, d=256), **4.3M params** | 8-layer pre-norm transformer, d=192, **6.2M params** |
| Steps | **15B** | 10B | 8.4B (2p) / 2.7B (4p) |
| Compute | 4x 8xB200 nodes, **~2400 B200-hours** | 8x H100, 3x 24h stages | 2x RTX 6000 Pro, ~19k SPS |
| Env | Rewrote in **Rust** | Rewrote in **Rust**, then ported to **C** for PufferLib | Rewrote in **JAX** |
| Reward | Terminal only, +1/-1, **gamma = 1.0** | Terminal, +1 win / +0.5 slow win / -1 loss | Terminal only, winner-take-all, zero-sum |
| Action space | Simplified: (source, target) pairs, not raw angles | Radically simplified: **no-op or all-in**, target ETA < 20 | **Semantic actions**: send-all / sortie / hold / kill-at-arrival |

## 2. The five things that actually mattered

**(a) Action-space simplification was the biggest single lever — for every one of them.**

This is the most consistent signal in the three writeups, and it cuts against intuition.

- 1st place *started* with the rawest possible action space (choose angle + fleet size
  directly). It learned "a semi-reasonable policy" that "was a far cry from being
  competitive." He changed it so the model picks a *target planet* and the engine computes the
  angle. That change is what made the run competitive; the 200M-parameter scaling came after.
- 2nd place cut the action space to **two intents per body**: no-op, or launch everything at a
  nearby target. He justified it empirically — he watched top-player replays and found they
  "launched at most one fleet per body," and "the two most common actions were by far no-op and
  all-in." He explicitly *tried* fractional ship counts (25/50/75/100%) and dropped them.
- 3rd place ran fixed fractions for most of the competition, then switched in the final week to
  **semantic actions** — "hold" (send exactly enough to conquer and hold for 8 rounds),
  "kill-at-arrival" (send exactly enough to capture on arrival, accounting for fleets already in
  flight). His words: "This increased learning speed by a lot."

The pattern is the same in all three: **move the arithmetic out of the policy and into a
solver, and let the policy choose intents.** The winners did not make their models learn how
many ships to send; they made a deterministic routine compute that, and had the model pick
*what outcome it wanted*. This is the transferable idea and it does not require RL at all.

**(b) A fast, exact simulator of the environment was the prerequisite for everything.**

All three rewrote the provided Python environment (Rust x2, JAX x1) and all three describe it
as a large fraction of the total work. 3rd place: computing his reachability tensor "was almost
as much work as the model itself." 2nd place needed a *second* rewrite (Rust -> C) to plug into
PufferLib. 1st place built pinned-memory buffers and multithreaded env stepping to feed the
GPUs.

3rd place's **reachability tensor** deserves its own note because it is the cleanest
expression of the idea. It is a `(B, P, P, S, 3)` tensor: for every (source planet, target
planet, semantic action) triple it stores the three numbers that fully determine a launch (ship
count, launch angle, arrival time). Everything downstream reads from it: the input features,
the action head, the ship counts, and the action mask. One derived-state object, computed once
per turn, that turns a physics problem into a lookup.

**(c) Terminal reward only. No shaping. Discount ~= 1.**

None of the three shaped rewards in their final runs. 3rd place "experimented with reward
shaping during the very early training phases" and shipped without it. 1st place used
gamma = 1.0 explicitly so the value head stays a clean win-probability estimate. 2nd place's
only deviation from +/-1 was a +0.5 for winning after the step limit — and that was a hack to
stop 4-player games stalling, not a shaping term.

Two of them named the cost of gamma = 1: the agent has no incentive to win *now*, so it
acquires a lead and stalls. 1st place calls this out as the thing he'd fix ("early truncation or
surrender mechanism") because it wastes rollout compute on decided games.

**(d) Action masking: the one genuinely surprising result.**

1st place tried a mask preventing obviously bad actions (launching into the sun) and **the
masked model trained worse.** His hypothesis: without the mask the model has to internally
learn the physics, and that representation helps elsewhere. He reintroduced the mask for late
fine-tuning and kept it at test time.

2nd and 3rd both masked throughout (2nd: `launch_mask` for unowned bodies, `target_mask[i,j]`
for unreachable pairs; 3rd: masks derived from the reachability tensor).

The consensus reading is: **mask at inference always; masking during training is a real
hyperparameter with a sign that is not obvious.**

**(e) Evaluation was a first-class engineering artifact, and everyone said self-play RL is
brutally noisy.**

- 2nd place built a **Rust local arena** early and used it all competition. Two modes:
  head-to-head, and a local leaderboard over a pool of agents using **OpenSkill** to mimic
  Kaggle's (undisclosed) matchmaking and rating.
- 3rd place ran 1024 eval games in parallel against prior checkpoints; promoted only when a
  checkpoint beat the incumbent. He also kept a **`zoo/` folder snapshotting whole pipeline
  versions** (features + model + env code together), because his feature code kept changing and
  faithful evaluation required freezing the entire pipeline, quirks and bugs included.
- 1st place gated checkpoint promotion at **>70% win rate** vs the previous best, and added
  policy-KL and value cross-entropy terms *against the previous best checkpoint* to stabilize
  training.
- 3rd place's closing caveat is worth quoting: *"Self-play RL is brutally noisy. With long
  convergence times and high run-to-run variance, you can realistically only test whether
  something speeds up learning, not whether it changes the final ceiling."*

## 3. Self-play, curriculum, and league play

- **1st place: pure self-play, no league, deliberately.** He skipped league play to maximize
  throughput and lists it as his main regret — the leaderboard's 2p/4p mix inverted after the
  deadline and self-play had over-specialized him. His single stabilizer was the
  >70%-vs-previous-best checkpoint gate plus KL anchoring to that checkpoint.
- **2nd place: IL first, then RL.** IL (behavioral cloning) on 5M samples from 20K replays got
  him to top 10. RL-finetuning from the IL checkpoint got him to top 5. Then, **five days before
  the deadline, he started from scratch with RL and it beat every IL-initialized model.** His
  regret is that he didn't try from-scratch sooner. He used a pool of frozen checkpoints for 2
  of 4 seats in 4p, then dropped even that.
- **3rd place: PFSP** (Prioritized Fictitious Self-Play — sample past opponents proportional to
  how hard they are to beat). His practical trick: rather than pay for separate eval games to
  estimate win rates for prioritization, he **fixed the sampled opponent for 2 consecutive PPO
  updates** and read win rates straight out of the rollouts, discarding open games at the
  switch. Free win-rate estimates at the cost of some terminal rewards.

**Note on 2nd place's IL, because it bears directly on our own two IL failures.** His IL
worked, and the reasons are specific and mechanical:

1. He filtered brutally — 20K episodes kept from 189K, requiring player score > 1500 (or a win
   against a >1500 player), pulling scores from the Meta Kaggle dataset.
2. He filtered on *behavior*, not just strength: he kept only episodes where the player used
   all-in actions exclusively, with a tolerance of 3 violating steps.
3. **He shrank the label space to match** — because he'd already decided the action space was
   {no-op, all-in}, the IL target was a clean binary launch head plus a target head.

That third point is the one we have never done. Filtering on rating alone (what our v2/v3 did)
leaves the policy trying to imitate an inconsistent mixture over a huge action space. Not
pursued in the 2026-08-16 window (see `baseline-comparison.md`'s "IL agent v3" section for why
IL was frozen) — parked as the first thing to try if the Strategy track
(`pokemon-tcg-ai-battle-challenge-strategy`, deadline 09-13) is entered.

## 4. ML vs. hand-engineering: where the line fell

Nobody shipped a rule-based agent in the top 3 — but the *heuristics did not disappear*, they
moved.

- 3rd place's four semantic actions are hand-written solvers. The network only picks which one.
- 1st place's engine computes launch angles in Rust from the (source, target) pair the net
  emits, "avoiding the sun and other planets when possible."
- 2nd place's whole feature representation is a **19-step hand-rolled forward simulation** of
  the environment under a no-op assumption, which implicitly encodes every in-flight fleet's
  arrival.

So the division of labour is consistent: **hand-code everything that is exactly computable,
learn only the parts that require judgement.** 1st place is the partial exception — he
explicitly bet on the Bitter Lesson and pushed the model to learn dynamics itself — but even he
conceded the raw action space and let the engine do the geometry.

Two more constraint-engineering details from 1st place worth remembering, because they are the
kind of thing that decides a submission:

- **Inference budget fallback**: when the CPU was slow enough that the 200M model would blow
  the time limit (about 8% of 4p games), he switched mid-game to a 5M model to play out the
  rest. Per his own critic, most such games were already decided, and the small model converted
  100% of its winning positions.
- **Size budget**: 4-bit NormalFloat quantization, group size 128, one fp16 scale per group, to
  fit 200M params in 100 MiB. The quantized model won ~40% head-to-head against the
  unquantized one — he took that loss because the bigger model was worth more than the
  precision.

## 5. Strategic mapping to PTCG AI Battle

**What does not transfer, stated plainly: we did not start an RL run.** Not pessimism —
arithmetic. 1st place: 2400 B200-hours, 15B steps. 3rd place, the most frugal: 8.4B steps on
2x RTX 6000 Pro over weeks — we had 6 days left at the time of this teardown. The Kaggle
simulation sandbox for this competition also has no numpy/pandas/sklearn (see `CLAUDE.md`'s
"sandbox almost certainly has no numpy" section) — no torch, no JAX either. A learned policy
has to run in pure stdlib Python at inference; a 4.3M-parameter transformer cannot be exported
that way the way a GBDT can (`src/pure_predictor.py`). Both of our IL attempts had already
underperformed rule-based, and the covariate-shift hypothesis for why had already been tested
and rejected (2026-08-09).

The finding that reframed the remaining runway: `cg/api.py` exposes a complete
forward-simulation API shipped inside every submission —

```python
search_begin(agent_observation, your_deck, your_prize,
             opponent_deck, opponent_prize, opponent_hand, opponent_active,
             manual_coin=False) -> SearchState
search_step(search_id, select: list[int]) -> SearchState   # apply an option, get next state
search_release(search_id) -> None
search_end() -> None
```

This is the Rust/JAX environment rewrite all three winners spent weeks on, handed to us in C,
already in the tarball — and `search_begin` takes explicit predicted contents for every hidden
zone (opponent deck, hand, prizes, face-down active), with `manual_coin=True` turning coin-flip
chance nodes into decision nodes. A determinization interface for a hidden-information game,
purpose-built.

`submissions/archaludon_search/main.py` already wired this up and measured, on our hardware:
`search_begin` 0.19 ms, `search_step` 0.13 ms, against a 600 s host budget over ~51 MAIN
decisions per battle (~11 s of thinking time available per decision, vs the layer's 1.5 s cap
and typical single-digit-ms actual spend — roughly 0.1% of available compute used per decision).

| Orbit Wars finding | PTCG AI Battle translation |
|---|---|
| Rewrite env in Rust/JAX for fast rollouts | Already have it: `search_begin`/`search_step`, 0.13 ms/step, in C |
| Reachability tensor (derived state everything reads) | Opponent-archetype determinization: classify their deck from visible cards, fill hidden zones from that real 60-card list |
| Semantic actions (hold / sortie / kill-at-arrival) | Candidate generation over *intents* rather than raw option indices |
| Terminal reward only, no shaping, gamma ~= 1 | Roll out to game end with the base policy on both sides and score win/loss — deletes the hand-weighted evaluator entirely |
| Action mask at inference, questionable in training | Keep every existing correctness guard; use masking only to prune candidates, never to invent preferences |
| Mask ablation surprised the winner | Any "obvious" guard should be measured for reachability before being credited — same lesson as our own `detect_matchup` guard (0/29,064 sampled) |
| Local arena + OpenSkill rating | Already have it: `src/ladder_eval.py`, frozen 7-agent panel, stdlib TrueSkill |
| `zoo/` snapshot of whole pipeline versions | Same discipline as our per-candidate `submissions/<name>/` dirs |
| Checkpoint gate at >70% vs previous best | Our within-archetype gate: mirror head-to-head at >=4000 battles, not frozen-panel mu (retro-validated 2026-08-09) |
| Inference-time fallback to a 5M model when out of budget | Time-bank the search: fall through to the base policy when the per-game budget runs low |
| Filter IL data by rating **and** behavior, shrink label space to match | The one untried IL fix — parked for the Strategy track, not this deadline |
| Self-play RL is brutally noisy; you can only measure speed-ups, not ceilings | Matches our own ladder noise floor (24-63 mu between settled readings) — ship nothing expected to move less |

## Outcome

The PIMC forward-search layer built on this teardown (candidate generation via
`search_begin`/`search_step` rollouts, replacing the hand-weighted `evaluate_board`) was
implemented and evaluated, and concluded a **negative result** — not shipped. See
`10-day-plan.md` for the measurement and the decision record. The evaluation infrastructure and
process lessons (frozen-panel ranking, reachability-before-blame, noise-floor discipline,
"don't ship anything expected to move less than the noise floor") carried forward and are now
standard practice across this repo regardless of the search layer's outcome.
