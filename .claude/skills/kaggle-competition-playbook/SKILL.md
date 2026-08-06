---
name: kaggle-competition-playbook
description: Use for Kaggle-competition-specific concerns for PTCG AI Battle that aren't about the battle engine itself — reading/scouting public notebooks and discussions, judging a public/leaderboard score before it's stabilized, debugging a submission that fails or scores oddly after Kaggle's hidden rerun (as opposed to a local run-battle failure), deciding what's safe to share publicly given this repo will go public, or structuring opponent-difficulty testing before submitting. Not for local battle simulation (use run-battle) or engine/rules questions (use game-engine-analyst).
---

# Kaggle Competition Playbook

Curated from a broader Kaggle-skills collection ([source](https://github.com/FrankS-IntelLab/agentic-kaggle-skill), evaluated in a private fork at `aleixlopezpascual/agentic-kaggle-skill`) and trimmed to what actually applies to **PTCG AI Battle**: a code-submission (`main.py` + `deck.csv`) game/agent competition, not a tabular or CSV-prediction one. The full source repo's tabular/CV/ensembling/producer-consumer-notebook material was dropped — none of it applies here since there's no training data, folds, or OOF predictions in this competition.

## Reference Map

- Read `references/rl-game-case-study.md` first — a past RL/battle competition with the same shape as PTCG AI Battle (agents battle, ELO-like rating, per-turn time limits). Its lessons (don't oversimplify, profile execution time after every feature addition, don't trust scores under 4 hours old) transfer almost directly.
- Read `references/01-competition-patterns.md` for the **score stabilization pattern** (leaderboard/ELO scores are inflated for the first 2-4 hours — don't react to an early score) and the **kernel execution modes** distinction (Run mode vs. Commit mode use different data mounts; a kernel that works when pushed can still fail differently when Kaggle actually scores it).
- Read `references/06-competition-types-submission-workflow.md` before submitting: it explains how to tell a pure code competition from a mixed one, and why submissions need explicit code/version linkage (`-k`/`-v` flags) rather than a bare file upload, if submitting via the Kaggle CLI.
- Read `references/code-competition-debugging.md` when a submission fails, times out, or scores unexpectedly *after* Kaggle's hidden rerun — as opposed to a failure caught locally by `run-battle`. Covers the failure taxonomy (missing output, resource limits, statefulness, hidden-data-shape assumptions) and a debug-patch-resubmit loop.
- Read `references/03-automation-patterns.md` for the **tiered opponent system** pattern: test a candidate agent against progressively harder opponent tiers (95%+ vs. baseline/random, 70%+ vs. intermediate, 55%+ vs. advanced) before spending a submission on it. This composes with the `run-battle` skill's local simulation — use `run-battle` to run the battles, this pattern to decide what "ready to submit" means. (The cronjob/`opencode`-specific automation in the rest of that file assumes a different tool stack — skip it; if recurring monitoring is ever needed, use this session's own `CronCreate`/`ScheduleWakeup` instead.)
- Read `references/competition-intel.md` when scouting public notebooks/discussions for technique ideas — matches the existing `notebooks/kaggle-research/pulled/` workflow. Treat public notebooks as scouting signals, not copy sources.
- Read `references/submission-endgame.md` for the general "done means scored, not just tested locally" discipline and what to record after each submission attempt.
- Read `references/information-sharing-policy.md` before this repo goes public: what's safe to share about a competition (code yes if rules allow, no private strategy from other teams, no leaderboard-probing writeups) — complements, doesn't replace, the repo's own `secrets-and-data-guard` skill.

## What Was Deliberately Left Out

Tabular workflow, cross-validation/OOF/metrics, image/text modeling, ensembling/stacking, Kaggle GPU-offload and producer/consumer notebook-dataset pipelines, and the ONNX-model-submission / audio-classification / environment-setup research notes — none apply to a rule-based or lightly-trained decision agent submitted as plain Python + a deck list. Revisit if the approach ever shifts to training a model that needs Kaggle-side compute or a supervised/RL training loop with real folds.
