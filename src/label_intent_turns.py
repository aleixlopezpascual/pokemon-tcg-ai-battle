"""Label each expert turn in the episode corpus with the intent that best explains it.

2nd place's actual working IL recipe (notebooks/kaggle-research/orbit-wars-teardown.md:126-140):
filter training episodes on BEHAVIOUR, not just rating, and shrink the label space to match the
decided action space. The five intents in submissions/archaludon_intent/main.py
(base/aggro/develop/snipe/survive) are that shrunk label space. For each turn in the corpus,
replay it under every intent and keep the turn only if one intent reproduces most of what the
expert actually did.

Usage:
    python3 src/label_intent_turns.py \\
        --records data/processed/il_records.jsonl \\
        --candidate submissions/archaludon_intent \\
        --out data/processed/il_intent_turns.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import global_features, sample_weight  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_candidate(dirname="archaludon_intent"):
    import importlib.util
    agent_dir = REPO_ROOT / "submissions" / dirname
    main_py = agent_dir / "main.py"
    engine_dir = REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission"
    if not main_py.exists():
        raise FileNotFoundError(f"no candidate at {main_py}")
    if not (engine_dir / "cg").is_dir():
        raise FileNotFoundError(f"no cg engine at {engine_dir}")
    for p in (str(engine_dir), str(agent_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("candidate_under_test", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_under_test"] = module
    spec.loader.exec_module(module)
    return module


def load_records(path):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def group_into_turns(records):
    """(episode_id, player) -> list of consecutive-turn groups, each a list of records."""
    by_actor = defaultdict(list)
    for r in records:
        by_actor[(r["episode_id"], r["player"])].append(r)

    for key, recs in by_actor.items():
        recs.sort(key=lambda r: r["step"])
        group = []
        current_turn = None
        for r in recs:
            if current_turn is not None and r.get("turn") != current_turn:
                if group:
                    yield key, group
                group = []
            current_turn = r.get("turn")
            group.append(r)
        if group:
            yield key, group


def label_turn(m, group):
    """Return (best_intent, matches, n) or None if the turn has no real decisions."""
    n = len(group)
    if n == 0:
        return None
    best_intent, best_matches = None, -1
    for intent in m.INTENTS:
        matches = 0
        for r in group:
            # Observation is a dataclass with a required (no-default) `logs` field (cg/api.py:441)
            # — to_dataclass's cls(**d) TypeErrors without it. Replay doesn't need real log
            # entries (choose_options_intent never reads obs.logs), so an empty list suffices.
            obs = m.to_observation_class({"select": r["select"], "current": r["current"], "logs": []})
            if obs.select is None or not obs.select.option:
                matches += 1  # no real decision here; every intent trivially "agrees"
                continue
            try:
                predicted = m.choose_options_intent(obs, intent)
            except Exception:
                predicted = None
            if predicted is not None and set(predicted) == set(r["action"]):
                matches += 1
        if matches > best_matches:
            best_intent, best_matches = intent, matches
    return best_intent, best_matches, n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default="data/processed/il_records.jsonl")
    ap.add_argument("--candidate", default="submissions/archaludon_intent")
    ap.add_argument("--out", default="data/processed/il_intent_turns.jsonl")
    ap.add_argument("--behavior-floor", type=float, default=0.8)
    ap.add_argument("--violation-tolerance", type=int, default=3)
    args = ap.parse_args()

    m = load_candidate(Path(args.candidate).name)
    records = list(load_records(args.records))
    print(f"loaded {len(records)} decision records")

    total_turns, kept = 0, 0
    per_intent_kept = defaultdict(int)
    match_rates = []
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as out_f:
        for (episode_id, player), group in group_into_turns(records):
            total_turns += 1
            result = label_turn(m, group)
            if result is None:
                continue
            intent, matches, n = result
            violations = n - matches
            rate = matches / n
            passes = rate >= args.behavior_floor or violations <= args.violation_tolerance
            if not passes:
                continue
            kept += 1
            per_intent_kept[intent] += 1
            match_rates.append(rate)
            first = group[0]
            features = global_features(first["select"], first["current"],
                                       actor_score=first.get("actor_score"),
                                       opp_score=first.get("opp_score"))
            weight = sample_weight(first.get("actor_score"), first.get("actor_reward"))
            out_f.write(json.dumps({
                "episode_id": episode_id, "player": player, "turn": first.get("turn"),
                "features": features, "intent": intent,
                "n_actions": n, "matches": matches, "weight": weight,
            }) + "\n")

    print(f"{total_turns} turns considered, {kept} kept ({kept / total_turns:.1%})")
    print(f"per-intent kept counts: {dict(per_intent_kept)}")
    if match_rates:
        print(f"mean behavior-match rate among kept turns: "
              f"{sum(match_rates) / len(match_rates):.1%}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
