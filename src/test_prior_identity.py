import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder_eval

FAILURES = []
STATES = "data/processed/selfplay_crustle/shard_*.jsonl"

def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} {detail}")

def skip(name, why):
    print(f"SKIP {name} ({why})")

def load_states(limit):
    import json
    out = []
    for shard in sorted(Path(".").glob(STATES)):
        with shard.open() as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("select") is None:
                    continue
                out.append({"select": rec["select"], "current": rec["current"], "logs": []})
                if len(out) >= limit:
                    return out
    return out

def load_pair():
    """`_load_agent_isolated` reads `ladder_eval._W["rb"]`, which only `_worker_init`
    populates -- it is worker-side state. Call `_worker_init` once here so the driver
    process can load agents the same way a pool worker does."""
    base_dir = Path("submissions/soutasakurai_libraryout_crustle").resolve()
    fork_dir = Path("submissions/crustle_il").resolve()
    rb = ladder_eval._load_run_battle_module()
    engine_dir = rb.find_engine_dir(base_dir, fork_dir, ladder_eval.DEFAULT_PANEL[0])
    ladder_eval._worker_init(str(engine_dir))
    return (ladder_eval._load_agent_isolated(base_dir, "base_crustle"),
            ladder_eval._load_agent_isolated(fork_dir, "fork_crustle_il"))

def main():
    states = load_states(5000)
    if len(states) < 500:
        skip("all", f"only {len(states)} dumped states; run ladder_eval --dump-states")
        return
    base, fork = load_pair()
    diffs = sum(1 for s in states if base(s) != fork(s))
    check("PRIOR_MARGIN=0 is byte-identical to base", diffs == 0,
          f"{diffs}/{len(states)} decisions differ")
    print(f"changed-decision rate: {100 * diffs / len(states):.2f}% "
          f"({diffs}/{len(states)})")

if __name__ == "__main__":
    main()
    sys.exit(1 if FAILURES else 0)
