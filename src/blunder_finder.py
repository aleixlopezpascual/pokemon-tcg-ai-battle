"""PIMC-oracle blunder finder for the Archaludon base heuristic.

Plays the UNMODIFIED base heuristic (no live search override) and, at every MAIN decision,
PIMC-scores the heuristic's actual chosen move against its best-ranked alternative using the
same oracle machinery built for the (now-parked) search layer in
submissions/archaludon_intent/main.py. Writes one JSONL record per decision:
{game_id, turn, chosen_option, chosen_value, best_alt_option, best_alt_value, gap, game_result}.
A large gap in a game the candidate went on to lose is a candidate blunder -- see
docs/superpowers/specs/2026-08-11-pimc-blunder-finder-design.md for the full design.

Run:
    python3 src/blunder_finder.py \\
        --candidate submissions/masamikobayashi_archaludon_cinderace \\
        --opponent submissions/soutasakurai_libraryout_crustle \\
        --games 500 --workers 8 \\
        --out data/processed/instrumentation/blunders_crustle.jsonl

Smoke-test first (few games, one worker, fast profile):
    python3 src/blunder_finder.py --candidate ... --opponent ... --games 3 --workers 1 \\
        --profile fast --out data/processed/instrumentation/blunders_smoke.jsonl
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

# Same reason as src/ladder_eval.py:66-68 and src/search_telemetry.py:31-34 -- must precede any
# numpy import in a worker.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_BATTLE_SCRIPT = REPO_ROOT / ".claude" / "skills" / "run-battle" / "scripts" / "run_battle.py"
ORACLE_DIR = REPO_ROOT / "submissions" / "archaludon_intent"

_STATE = {}


def _load_run_battle_module():
    spec = importlib.util.spec_from_file_location("run_battle_mod", RUN_BATTLE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_module(main_py, module_name):
    """Load one agent's `main.py` without letting its helper modules leak into the next agent's.

    Submissions bundle same-named helpers (e.g. `il_intent_pure.py`). If two agents are loaded
    into one process, the first agent's cached `sys.modules["il_intent_pure"]` will silently
    corrupt the second agent's state. So: snapshot `sys.path` and `sys.modules`, do the import,
    restore the path, and evict any newly-imported module that came from this agent's bundle.
    """
    agent_dir = Path(main_py).parent.resolve()
    saved_path = list(sys.path)
    before = set(sys.modules)
    try:
        sys.path.insert(0, str(agent_dir))
        spec = importlib.util.spec_from_file_location(module_name, main_py)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path[:] = saved_path
        # Evict any helper module imported from inside this agent's directory.
        for name in set(sys.modules) - before:
            if name == module_name:
                continue
            imported_mod = sys.modules.get(name)
            origin = getattr(imported_mod, "__file__", None)
            if not origin:
                continue
            try:
                Path(origin).resolve().relative_to(agent_dir)
            except ValueError:
                continue  # not from this agent's bundle — genuinely shared, keep it cached
            del sys.modules[name]


def _worker_init(engine_dir, cand_dir, opp_dir, profile):
    """Import the candidate, the oracle, and the opponent once per process.

    The oracle module (`archaludon_intent/main.py`) is imported separately from the candidate so
    that PIMC scoring machinery is available even when `--candidate` is a lean fork (like
    `archaludon_lossfix`) that never had the search layer's Tasks 5-10 code appended to it. Only
    the oracle needs `PTCG_SEARCH_PROFILE` set before import -- the candidate and opponent don't
    read that env var.
    """
    os.environ["PTCG_SEARCH_PROFILE"] = profile
    sys.path.insert(0, str(engine_dir))
    from cg.game import battle_start, battle_finish, battle_select  # noqa: F401
    rb = _load_run_battle_module()
    _STATE["rb"] = rb
    _STATE["battle_start"] = battle_start
    _STATE["battle_select"] = battle_select
    _STATE["battle_finish"] = battle_finish
    _STATE["cand_mod"] = _import_module(Path(cand_dir) / "main.py", "cand_main")
    _STATE["oracle_mod"] = _import_module(ORACLE_DIR / "main.py", "oracle_main")
    _STATE["opp_mod"] = _import_module(Path(opp_dir) / "main.py", "opp_main")
    _STATE["cand_deck"] = rb.load_deck(Path(cand_dir))
    _STATE["opp_deck"] = rb.load_deck(Path(opp_dir))


def _base_agent_move(cand, oracle, obs_dict):
    """`archaludon_intent.agent()`'s bookkeeping and fallback, without the search_reorder call.

    Mirrors the same tracking update onto `oracle` (a separately-loaded module instance with its
    own globals) so `oracle._opp_last_attack_id`/`_cur_turn_logs` stay in sync with the game the
    candidate is actually playing -- otherwise `oracle.rank_options`/`_pimc_score_lines` (and the
    rollout plies that read them) would silently score every decision as if the opponent had never
    attacked.
    """
    obs = cand.to_observation_class(obs_dict)
    if obs.select is None:
        cand._opp_last_attack_id = None
        cand._cur_turn_logs.clear()
        oracle._opp_last_attack_id = None
        oracle._cur_turn_logs.clear()
        return cand.read_deck_csv()
    cand._update_opp_attack_tracking(obs)
    oracle._update_opp_attack_tracking(oracle.to_observation_class(obs_dict))
    if not obs.select.option:
        return []
    try:
        return cand.choose_options(obs)
    except Exception:
        import random
        n_options = len(obs.select.option)
        k = max(obs.select.minCount, min(obs.select.maxCount, n_options))
        return random.sample(list(range(n_options)), k) if k > 0 else []


def _diagnose_decision(oracle, cand_deck, obs_dict, chosen, k=4):
    """PIMC-score `chosen`'s first move against its top-(k-1) ranked alternatives.

    Returns a dict matching the JSONL record shape (minus game_id/game_result, filled by the
    caller), or None if this wasn't a scoreable single-select MAIN decision. Never raises -- any
    internal error is caught and reported as a record with best_alt_value=None, matching the
    design's fail-closed discipline (this is read-only instrumentation, it must never affect the
    real game already decided by `chosen`).
    """
    obs = oracle.to_observation_class(obs_dict)
    if obs.select is None or obs.select.context != oracle.SelectContext.MAIN:
        return None
    if obs.select.maxCount != 1 or not chosen:
        return None
    chosen_option = chosen[0]
    try:
        ranked = oracle.rank_options(obs)  # [(score, index, reason), ...] best-first
        alt_indices = [i for _, i, _ in ranked if i != chosen_option][:k - 1]
        lines = [(chosen_option, chosen_option)] + [(i, i) for i in alt_indices]
        my_index = obs.current.yourIndex
        deadline = time.time() + oracle.SEARCH_TIME_BUDGET
        values = oracle._pimc_score_lines(obs, cand_deck, my_index, lines, deadline)
    except Exception:
        return {
            "turn": getattr(obs.current, "turn", None),
            "chosen_option": chosen_option,
            "chosen_value": None, "best_alt_option": None, "best_alt_value": None, "gap": None,
        }
    chosen_value = values.get(chosen_option, (None, 0))[0]
    alt_values = {i: v[0] for i, v in values.items() if i != chosen_option}
    best_alt_option = max(alt_values, key=alt_values.get) if alt_values else None
    best_alt_value = alt_values.get(best_alt_option) if best_alt_option is not None else None
    gap = (best_alt_value - chosen_value
           if chosen_value is not None and best_alt_value is not None else None)
    return {
        "turn": getattr(obs.current, "turn", None),
        "chosen_option": chosen_option,
        "chosen_value": chosen_value,
        "best_alt_option": best_alt_option,
        "best_alt_value": best_alt_value,
        "gap": gap,
    }


def _play_one(cand, oracle, opp, cand_deck, cand_first, game_id, records):
    bs, bsel, bfin = _STATE["battle_start"], _STATE["battle_select"], _STATE["battle_finish"]
    cd, od = _STATE["cand_deck"], _STATE["opp_deck"]
    decks = (cd, od) if cand_first else (od, cd)
    obs, start_data = bs(decks[0], decks[1])
    if obs is None:
        print(f"battle start failed: errorPlayer={start_data.errorPlayer} "
              f"errorType={start_data.errorType}", file=sys.stderr)
        return
    cand_index = 0 if cand_first else 1
    game_records = []
    try:
        while obs["current"]["result"] == -1:
            actor = obs["current"]["yourIndex"]
            if actor == cand_index:
                chosen = _base_agent_move(cand, oracle, obs)
                diag = _diagnose_decision(oracle, cand_deck, obs, chosen)
                if diag is not None:
                    diag["game_id"] = game_id
                    game_records.append(diag)
                move = chosen
            else:
                move = opp.agent(obs)
            obs = bsel(move)
        winner = obs["current"]["result"]
    finally:
        bfin()
    result = "draw" if winner == -2 else ("win" if winner == cand_index else "loss")
    for rec in game_records:
        rec["game_result"] = result
    records.extend(game_records)


def _play_chunk(task):
    n, offset = task
    cand, oracle, opp = _STATE["cand_mod"], _STATE["oracle_mod"], _STATE["opp_mod"]
    cand_deck = _STATE["cand_deck"]
    records = []
    t0 = time.time()
    for i in range(n):
        _play_one(cand, oracle, opp, cand_deck, (offset + i) % 2 == 0, offset + i, records)
    return records, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--games", type=int, default=500)
    ap.add_argument("--workers", type=int,
                    default=max(1, min(8, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--profile", choices=["fast", "ship"], default="ship",
                    help="PIMC resolution: ship=40 draws/10s (default, cost is not a constraint "
                         "for this project), fast=12 draws/3s (for quick smoke runs only)")
    ap.add_argument("--out", required=True, help="write JSONL records here")
    args = ap.parse_args()

    cand = Path(args.candidate).resolve()
    opp = Path(args.opponent).resolve()
    rb = _load_run_battle_module()
    engine_dir = rb.find_engine_dir(
        cand, opp, REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission")

    workers = args.workers
    per = max(1, args.games // workers)
    tasks = [(per, i * per) for i in range(workers)]
    init = (str(engine_dir), str(cand), str(opp), args.profile)

    if workers == 1:
        _worker_init(*init)
        results = [_play_chunk(t) for t in tasks]
    else:
        with Pool(workers, initializer=_worker_init, initargs=init) as pool:
            results = list(pool.imap_unordered(_play_chunk, tasks))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total_records = 0
    total_seconds = sum(r[1] for r in results)
    with out.open("w") as f:
        for records, _ in results:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
                total_records += 1
    games = sum(t[0] for t in tasks)
    print(f"games={games} decisions={total_records} cpu_seconds={total_seconds:.1f} -> {out}")


if __name__ == "__main__":
    main()
