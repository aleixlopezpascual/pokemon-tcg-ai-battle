#!/usr/bin/env python3
"""Run N battles between two Pokemon TCG AI Battle agents using the competition's cg engine.

Each agent directory must contain main.py (with an agent(obs_dict) function) and
deck.csv (60 card IDs, one per line). The cg/ engine directory is auto-discovered
next to the candidate, the opponent, or the bundled sample_submission.
"""
import argparse
import importlib.util
import sys
from pathlib import Path


def load_deck(agent_dir: Path) -> list[int]:
    lines = (agent_dir / "deck.csv").read_text().split("\n")
    return [int(lines[i]) for i in range(60)]


def load_agent(main_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.agent


def find_engine_dir(*candidates: Path) -> Path:
    for c in candidates:
        if (c / "cg").is_dir():
            return c
    raise SystemExit(
        "Could not find a cg/ engine directory next to the candidate, opponent, "
        "or the bundled sample_submission. Pass --opponent explicitly or make sure "
        "data/raw/sample_submission/sample_submission exists (download the competition data)."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, help="Directory with the candidate's main.py and deck.csv")
    parser.add_argument(
        "--opponent",
        help="Directory with the opponent's main.py and deck.csv (default: bundled sample_submission random agent)",
    )
    parser.add_argument("--battles", type=int, default=10)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[4]
    candidate_dir = Path(args.candidate).resolve()
    default_opponent = repo_root / "data" / "raw" / "sample_submission" / "sample_submission"
    opponent_dir = Path(args.opponent).resolve() if args.opponent else default_opponent

    engine_dir = find_engine_dir(candidate_dir, opponent_dir, default_opponent)
    sys.path.insert(0, str(engine_dir))
    from cg.game import battle_start, battle_finish, battle_select  # noqa: E402

    candidate_agent = load_agent(candidate_dir / "main.py", "candidate_main")
    opponent_agent = load_agent(opponent_dir / "main.py", "opponent_main")
    candidate_deck = load_deck(candidate_dir)
    opponent_deck = load_deck(opponent_dir)

    wins = {"candidate": 0, "opponent": 0}
    errors = 0

    for i in range(args.battles):
        candidate_first = i % 2 == 0
        if candidate_first:
            deck_a, deck_b = candidate_deck, opponent_deck
            agent_a, agent_b = candidate_agent, opponent_agent
        else:
            deck_a, deck_b = opponent_deck, candidate_deck
            agent_a, agent_b = opponent_agent, candidate_agent

        obs, start_data = battle_start(deck_a, deck_b)
        if obs is None:
            errors += 1
            print(f"battle {i}: failed to start (errorPlayer={start_data.errorPlayer}, errorType={start_data.errorType})")
            continue

        agents = [agent_a, agent_b]
        while obs["current"]["result"] == -1:
            your_index = obs["current"]["yourIndex"]
            select_list = agents[your_index](obs)
            obs = battle_select(select_list)

        winner_slot = obs["current"]["result"]  # 0 or 1, referring to deck_a/deck_b
        winner = "candidate" if (winner_slot == 0) == candidate_first else "opponent"
        wins[winner] += 1
        battle_finish()
        first = "candidate" if candidate_first else "opponent"
        print(f"battle {i}: first={first} winner={winner}")

    total = args.battles - errors
    print()
    if total:
        print(f"candidate wins: {wins['candidate']}/{total} ({wins['candidate']/total:.1%})")
        print(f"opponent  wins: {wins['opponent']}/{total} ({wins['opponent']/total:.1%})")
    if errors:
        print(f"errors: {errors} (deck likely invalid per PTCG deck-legality rules)")


if __name__ == "__main__":
    main()
