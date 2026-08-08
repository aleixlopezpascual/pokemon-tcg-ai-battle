"""Multi-opponent local evaluation harness.

Single-opponent `run-battle` testing has been repeatedly misleading in this competition:
a candidate can crush one local opponent and still score far below (or above) a candidate
that lost that exact matchup, once measured on the real ladder. This harness runs a candidate
against a small roster of real, diverse agents (not just the random baseline) and reports a
per-opponent win rate with a Wilson 95% confidence interval, plus a pooled aggregate — a better
filter than any single matchup, though still not a substitute for a real ladder reading.

Usage:
    python src/local_eval.py --candidate submissions/masamikobayashi_archaludon_cinderace
    python src/local_eval.py --candidate submissions/soutasakurai_libraryout_crustle --battles 30
    python src/local_eval.py --candidate submissions/il_agent_v2b --save-losses /tmp/losses
    python src/local_eval.py --candidate submissions/il_agent_v2b --repeats 3 --battles 10
"""

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_BATTLE_SCRIPT = REPO_ROOT / ".claude" / "skills" / "run-battle" / "scripts" / "run_battle.py"

DEFAULT_OPPONENTS = [
    REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission",
    REPO_ROOT / "submissions" / "kiyota_mega_lucario_ex",
    REPO_ROOT / "submissions" / "masamikobayashi_archaludon_cinderace",
    REPO_ROOT / "submissions" / "soutasakurai_libraryout_crustle",
    REPO_ROOT / "submissions" / "il_agent_v2b",
    REPO_ROOT / "submissions" / "aristophanivan_probablity_v2",
    REPO_ROOT / "submissions" / "biohack44_alakazam_dunsparce",
]


def _load_run_battle_module():
    spec = importlib.util.spec_from_file_location("run_battle", RUN_BATTLE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_battle"] = module
    spec.loader.exec_module(module)
    return module


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def check_stability(repeat_results: list[tuple[int, int]]) -> bool:
    if len(repeat_results) < 2:
        return True
    cis = [wilson_interval(wins, games) if games else (0.0, 0.0) for wins, games in repeat_results]
    for i, (lo_i, hi_i) in enumerate(cis):
        for j, (lo_j, hi_j) in enumerate(cis):
            if i < j and (hi_i < lo_j or hi_j < lo_i):
                return False
    return True


def run_matchup(rb, candidate_dir: Path, opponent_dir: Path, battles: int, engine_dir: Path,
                 save_losses_dir: Path | None = None, repeat_index: int = 0):
    sys.path.insert(0, str(engine_dir))
    from cg.game import battle_start, battle_select, battle_finish, visualize_data

    candidate_agent = rb.load_agent(candidate_dir / "main.py", "candidate_main")
    opponent_agent = rb.load_agent(opponent_dir / "main.py", "opponent_main")
    candidate_deck = rb.load_deck(candidate_dir)
    opponent_deck = rb.load_deck(opponent_dir)

    wins, errors = 0, 0
    for i in range(battles):
        candidate_first = i % 2 == 0
        deck_a, deck_b = (candidate_deck, opponent_deck) if candidate_first else (opponent_deck, candidate_deck)
        agent_a, agent_b = (candidate_agent, opponent_agent) if candidate_first else (opponent_agent, candidate_agent)

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
            out_path = save_losses_dir / f"{opponent_dir.name}_r{repeat_index}_battle{i}.json"
            out_path.write_text(json.dumps(vis))
        battle_finish()

    return wins, errors, battles - errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--opponents", nargs="*", help="Override the default opponent roster (directories)")
    parser.add_argument("--battles", type=int, default=30, help="Battles per matchup (default 30)")
    parser.add_argument("--save-losses", help="Directory to dump lost-battle replays as JSON (drag into the community visualizer.html)")
    parser.add_argument("--repeats", type=int, default=1, help="Independent repeats per matchup, to check ranking stability (default 1)")
    args = parser.parse_args()

    if args.repeats < 1:
        parser.error("--repeats must be >= 1")

    save_losses_dir = Path(args.save_losses).resolve() if args.save_losses else None
    if save_losses_dir is not None and save_losses_dir.exists() and not save_losses_dir.is_dir():
        parser.error(f"--save-losses path exists and is not a directory: {save_losses_dir}")

    rb = _load_run_battle_module()
    candidate_dir = Path(args.candidate).resolve()
    opponents = [Path(p).resolve() for p in args.opponents] if args.opponents else DEFAULT_OPPONENTS
    opponents = [o for o in opponents if o.resolve() != candidate_dir]

    engine_dir = rb.find_engine_dir(candidate_dir, *opponents)

    total_wins, total_games = 0, 0
    rows = []
    for opponent_dir in opponents:
        repeat_results = []
        pooled_errors = 0
        for repeat_index in range(args.repeats):
            wins, errors, games = run_matchup(
                rb, candidate_dir, opponent_dir, args.battles, engine_dir, save_losses_dir, repeat_index
            )
            repeat_results.append((wins, games))
            pooled_errors += errors
        pooled_wins = sum(w for w, g in repeat_results)
        pooled_games = sum(g for w, g in repeat_results)
        stable = check_stability(repeat_results)
        lo, hi = wilson_interval(pooled_wins, pooled_games) if pooled_games else (0.0, 0.0)
        rows.append((opponent_dir.name, pooled_wins, pooled_games, pooled_errors, lo, hi, stable, repeat_results))
        total_wins += pooled_wins
        total_games += pooled_games

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

    print()
    if total_games:
        lo, hi = wilson_interval(total_wins, total_games)
        pooled_pct = total_wins / total_games * 100
        print(f"pooled: {total_wins}/{total_games} ({pooled_pct:.1f}%) 95% CI [{lo*100:.1f}, {hi*100:.1f}]")


if __name__ == "__main__":
    main()
