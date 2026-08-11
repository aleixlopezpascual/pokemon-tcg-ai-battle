"""Per-decision telemetry for the forward-search layer.

`ladder_eval.py` answers "is this candidate stronger". This answers "is the search layer doing
anything at all, and does its estimator have the resolution to justify what it does". CLAUDE.md's
standing rule is to measure a branch's reachability before crediting or blaming it; the 2026-08-10
PIMC post-mortem needed a throwaway uncommitted script to do that, so this is the committed
version.

Run:
    python3 src/search_telemetry.py \\
        --candidate submissions/archaludon_intent \\
        --opponent submissions/soutasakurai_libraryout_crustle \\
        --games 60 --workers 8 \\
        --out data/processed/instrumentation/intent_vs_crustle.json

Capture test fixtures instead of a summary:
    python3 src/search_telemetry.py --candidate ... --opponent ... --games 5 \\
        --dump-main-states data/processed/instrumentation/main_states_crustle.jsonl
"""

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

# Same reason as src/ladder_eval.py:66-68 — must precede any numpy import in a worker.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_BATTLE_SCRIPT = REPO_ROOT / ".claude" / "skills" / "run-battle" / "scripts" / "run_battle.py"

_STATE = {}


def _load_run_battle_module():
    spec = importlib.util.spec_from_file_location("run_battle_mod", RUN_BATTLE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _worker_init(engine_dir, cand_dir, opp_dir, trace, dump_states):
    """Import both agents once per process, with tracing enabled before the candidate loads."""
    os.environ["PTCG_SEARCH_TRACE"] = "1" if trace else "0"
    os.environ.setdefault("PTCG_SEARCH_PROFILE", "fast")
    sys.path.insert(0, str(engine_dir))
    from cg.game import battle_start, battle_finish, battle_select  # noqa: F401
    rb = _load_run_battle_module()
    _STATE["rb"] = rb
    _STATE["battle_start"] = battle_start
    _STATE["battle_select"] = battle_select
    _STATE["battle_finish"] = battle_finish
    _STATE["cand_mod"] = _import_agent(cand_dir, "cand_main")
    _STATE["opp_mod"] = _import_agent(opp_dir, "opp_main")
    _STATE["cand_deck"] = rb.load_deck(Path(cand_dir))
    _STATE["opp_deck"] = rb.load_deck(Path(opp_dir))
    _STATE["dump_states"] = dump_states


def _import_agent(agent_dir, module_name):
    main_py = Path(agent_dir) / "main.py"
    sys.path.insert(0, str(agent_dir))
    spec = importlib.util.spec_from_file_location(module_name, main_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _play_chunk(task):
    """Play `n` battles, returning (wins, seconds, stats_delta, traces, captured_states)."""
    n, offset = task
    cand, opp = _STATE["cand_mod"], _STATE["opp_mod"]
    before = dict(getattr(cand, "_search_stats", {}))
    traces, captured = [], []
    wins = 0
    t0 = time.time()
    for i in range(n):
        cand_first = (offset + i) % 2 == 0
        result = _play_one(cand, opp, cand_first, captured)
        if result == "candidate":
            wins += 1
    after = dict(getattr(cand, "_search_stats", {}))
    delta = {k: after.get(k, 0) - before.get(k, 0) for k in after}
    traces.extend(getattr(cand, "_search_trace", []))
    if hasattr(cand, "_search_trace"):
        cand._search_trace.clear()
    return wins, time.time() - t0, delta, traces, captured


def _play_one(cand, opp, cand_first, captured):
    bs, bsel, bfin = _STATE["battle_start"], _STATE["battle_select"], _STATE["battle_finish"]
    cd, od = _STATE["cand_deck"], _STATE["opp_deck"]
    decks = (cd, od) if cand_first else (od, cd)
    # battle_start returns (obs, StartData); obs is None on a deck-validation failure
    # (see cg/game.py:37-38 and .claude/skills/run-battle/scripts/run_battle.py:73-76).
    obs, start_data = bs(decks[0], decks[1])
    if obs is None:
        print(f"battle start failed: errorPlayer={start_data.errorPlayer} "
              f"errorType={start_data.errorType}", file=sys.stderr)
        return "start_failed"
    cand_index = 0 if cand_first else 1
    try:
        while obs["current"]["result"] == -1:
            actor = obs["current"]["yourIndex"]
            mod = cand if actor == cand_index else opp
            if (_STATE["dump_states"] and actor == cand_index
                    and obs.get("select") and len(captured) < 200):
                snap = json.loads(json.dumps(obs))
                snap.pop("search_begin_input", None)
                captured.append(snap)
            obs = bsel(mod.agent(obs))
        winner = obs["current"]["result"]
    finally:
        bfin()
    return "candidate" if winner == cand_index else "opponent"


def _summarize(traces):
    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return statistics.fmean(vals) if vals else None

    pimc = [t for t in traces if not t.get("lethal")]
    gaps = [t["best_value"] - t["base_value"] for t in pimc
            if t.get("best_value") is not None and t.get("base_value") is not None]
    return {
        "searches": len(traces),
        "lethal_searches": sum(1 for t in traces if t.get("lethal")),
        "pimc_searches": len(pimc),
        "multi_option_share": (
            sum(1 for t in traces if (t.get("n_options") or 0) > 1) / len(traces)
            if traces else None),
        "mean_options": _mean([t.get("n_options") for t in traces]),
        "mean_candidates": _mean([t.get("n_candidates") for t in traces]),
        "mean_distinct_lines": _mean([t.get("n_distinct") for t in traces]),
        "mean_draws_per_line": _mean([t.get("draws_per_line") for t in traces]),
        "override_share": (sum(1 for t in pimc if t.get("changed")) / len(pimc)
                           if pimc else None),
        "budget_cut_share": (sum(1 for t in traces if t.get("budget_cut")) / len(traces)
                             if traces else None),
        "mean_value_gap": _mean(gaps),
        "value_gap_p90": (sorted(gaps)[int(0.9 * (len(gaps) - 1))] if gaps else None),
        "archetype_share": {
            name: sum(1 for t in traces if t.get("archetype") == name) / len(traces)
            for name in {t.get("archetype") for t in traces}
        } if traces else {},
        "mean_seconds_per_search": _mean([t.get("elapsed") for t in traces]),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--games", type=int, default=60)
    ap.add_argument("--workers", type=int,
                    default=max(1, min(8, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--out", help="write the JSON summary here")
    ap.add_argument("--dump-main-states",
                    help="write captured candidate MAIN observations here as JSONL, then exit")
    args = ap.parse_args()

    cand = Path(args.candidate).resolve()
    opp = Path(args.opponent).resolve()
    rb = _load_run_battle_module()
    engine_dir = rb.find_engine_dir(
        cand, opp, REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission")

    dump = bool(args.dump_main_states)
    workers = 1 if dump else args.workers
    per = max(1, args.games // workers)
    tasks = [(per, i * per) for i in range(workers)]

    # Set here (not only inside _worker_init) so the main process's own os.environ reflects the
    # profile actually used by the workers — with workers > 1, _worker_init's setdefault runs in
    # the pool subprocess and never touches this process, which would otherwise make the summary's
    # "profile" field silently wrong (it reported "ship" while games ran on "fast").
    os.environ.setdefault("PTCG_SEARCH_PROFILE", "fast")

    init = (str(engine_dir), str(cand), str(opp), True, dump)
    if workers == 1:
        _worker_init(*init)
        results = [_play_chunk(t) for t in tasks]
    else:
        with Pool(workers, initializer=_worker_init, initargs=init) as pool:
            results = list(pool.imap_unordered(_play_chunk, tasks))

    wins = sum(r[0] for r in results)
    seconds = sum(r[1] for r in results)
    games = sum(t[0] for t in tasks)
    stats = {}
    traces, captured = [], []
    for _, _, delta, tr, cap in results:
        for k, v in delta.items():
            stats[k] = stats.get(k, 0) + v
        traces.extend(tr)
        captured.extend(cap)

    if dump:
        out = Path(args.dump_main_states)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(json.dumps(c) for c in captured) + "\n")
        print(f"wrote {len(captured)} MAIN observations -> {out}")
        return

    summary = {
        "candidate": cand.name,
        "opponent": opp.name,
        "games": games,
        "wins": wins,
        "win_rate": wins / games if games else None,
        "profile": os.environ.get("PTCG_SEARCH_PROFILE", "ship"),
        "cpu_seconds_per_game": seconds / games if games else None,
        "searches_per_game": len(traces) / games if games else None,
        "stats": stats,
        "decisions": _summarize(traces),
    }
    print(json.dumps(summary, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(summary, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
