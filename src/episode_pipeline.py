"""Parse downloaded Kaggle episode replays into raw (observation, action) imitation-learning records.

Kaggle-environments records the action an agent produced *in response to* step i's observation
inside step i+1's entry for that same player — not inside step i's own entry. (Verified: pairing
same-step action with same-step observation produces ~22% of records with an action index out of
range or violating minCount/maxCount, i.e. provably impossible; the i -> i+1 pairing produces 0%.)

Two decision kinds per (player, step):
  - Deck submission: `observation.select is None`, the *next* step's action is the 60-card deck.
  - Mid-game decision: `observation.select` describes the legal options, the *next* step's
    action is the list of chosen option indices (respecting minCount/maxCount — may legitimately
    be empty when minCount == 0, e.g. declining an optional effect).

This script extracts every mid-game decision from every downloaded episode (both players — every
recorded player's move is imitation signal, not just a specific team's) into one JSONL file for
src/features.py to turn into a fixed-width training set. Deck submissions are skipped here (we're
not learning deck construction, just the mid-game policy).

Usage:
    python src/episode_pipeline.py --episodes-dir data/raw/episodes --out data/processed/il_records.jsonl
"""

import argparse
import json
from pathlib import Path


def extract_records(episode_path: Path):
    data = json.loads(episode_path.read_text())
    return extract_records_from_dict(data)


def _player_deck(steps, player_idx):
    """Find a player's submitted 60-card deck within this episode (first deck-submission step)."""
    for i in range(len(steps) - 1):
        entry = steps[i][player_idx]
        obs = entry.get("observation")
        if obs and obs.get("select") is None:
            action = steps[i + 1][player_idx].get("action") or []
            if len(action) == 60:
                return tuple(sorted(action))
    return None


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
                continue  # deck submission or malformed — skip

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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--episodes-dir", default="data/raw/episodes")
    parser.add_argument("--out", default="data/processed/il_records.jsonl")
    args = parser.parse_args()

    episodes_dir = Path(args.episodes_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    episode_files = sorted(episodes_dir.rglob("*.json"))
    total_records = 0
    total_episodes = 0
    skipped = 0
    total_tripwire = 0

    with out_path.open("w") as out_f:
        for episode_path in episode_files:
            try:
                records, tripwire_failures = extract_records(episode_path)
            except (json.JSONDecodeError, KeyError) as e:
                skipped += 1
                print(f"skipping {episode_path.name}: {e}")
                continue
            for r in records:
                out_f.write(json.dumps(r) + "\n")
            total_records += len(records)
            total_episodes += 1
            total_tripwire += tripwire_failures

    print(
        f"parsed {total_episodes} episodes ({skipped} skipped) -> {total_records} decision records "
        f"({total_tripwire} tripwire failures, should be 0) -> {out_path}"
    )
    if total_tripwire:
        print("WARNING: tripwire failures detected — the (observation, action) pairing bug may have regressed.")


if __name__ == "__main__":
    main()
