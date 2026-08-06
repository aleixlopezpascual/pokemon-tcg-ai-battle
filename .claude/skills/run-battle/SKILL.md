---
name: run-battle
description: Run Pokemon TCG AI Battle simulations between two agents (a candidate main.py/deck.csv and an opponent, defaulting to the competition's sample random agent) using the competition's cg battle engine, and report win rate. Use this whenever the user wants to test, evaluate, or benchmark a Pokemon TCG agent, asks "how does my agent do against random", wants a win rate, or wants to sanity-check a submission before uploading it to Kaggle.
---

# Run Battle

Simulates N games of the Pokemon TCG AI Battle competition between two agents locally,
without needing to submit to Kaggle. Useful for quickly checking whether a new agent
(deck + strategy) beats the baseline random agent, or comparing two candidate agents
against each other.

## How it works

The competition ships a compiled battle engine (`cg/`, a `ctypes`-wrapped shared library)
alongside a Python wrapper (`cg/game.py`, `cg/api.py`). `scripts/run_battle.py` drives that
engine directly:

1. Loads each agent's `deck.csv` (60 card IDs) and `main.py` (must expose `agent(obs_dict) -> list[int]`).
2. Calls `battle_start(deckA, deckB)` to start a battle, then repeatedly calls whichever
   agent's `agent()` function `obs["current"]["yourIndex"]` says should act, feeding its
   return value into `battle_select()`, until `obs["current"]["result"]` is no longer `-1`.
3. Alternates which agent goes first each battle (first-player advantage is real in TCGs),
   and tallies wins.

## Usage

```bash
python .claude/skills/run-battle/scripts/run_battle.py \
  --candidate path/to/agent_dir \
  [--opponent path/to/other_agent_dir] \
  [--battles 20]
```

- `--candidate` (required): a directory containing `main.py` and `deck.csv` — e.g. a
  submission you're iterating on under `submissions/` or `notebooks/`.
- `--opponent` (optional): another agent directory in the same shape. Defaults to the
  competition's bundled `sample_submission` (a random agent) at
  `data/raw/sample_submission/sample_submission`, which requires the competition data to
  have been downloaded (`data/raw/`, gitignored, local-only).
- `--battles` (optional, default 10): number of games to simulate.

The engine's `cg/` directory is auto-discovered next to whichever of candidate/opponent/
default-opponent has one — you don't need to copy it around manually.

## Interpreting results

Output is a per-battle line (`battle N: first=<candidate|opponent> winner=<candidate|opponent>`)
followed by a win-rate summary. A `battle N: failed to start (...)` line means the
candidate's `deck.csv` violates PTCG deck-legality rules (e.g. wrong card count, illegal
duplicates, no Basic Pokémon) — the engine rejects the battle before it starts rather than
crashing mid-game, so treat this as "fix the deck," not "fix the agent logic."

## When something looks wrong

If battles error out or hang, don't guess — the engine's real behavior is defined by
`cg/api.py` (the `Observation`/`Select`/`Option` dataclasses) and `cg/game.py` (the
`battle_start`/`battle_select`/`battle_finish` functions actually called here). Read those
directly, or delegate to the `game-engine-analyst` subagent if the question is about game
rules or option semantics rather than this script's plumbing.
