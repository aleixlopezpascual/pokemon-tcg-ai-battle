"""Tests for the intent-based search layer in submissions/archaludon_intent/main.py.

Run: python3 src/test_search_layer.py

The candidate lives in a gitignored directory and the observation fixtures live under
data/processed/ (also gitignored), so every test skips cleanly when its inputs are absent.
Regenerate fixtures with:
    python3 src/search_telemetry.py --candidate submissions/archaludon_intent \\
        --opponent submissions/soutasakurai_libraryout_crustle --games 5 \\
        --dump-main-states data/processed/instrumentation/main_states_crustle.jsonl
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FAILURES = []
SKIPPED = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}   {detail}")
        FAILURES.append(name)


def skip(name, why):
    print(f"  skip  {name}   ({why})")
    SKIPPED.append(name)


def _load_candidate(dirname="archaludon_intent"):
    """Import the candidate's main.py by path. Returns the module, or None if unavailable."""
    agent_dir = REPO_ROOT / "submissions" / dirname
    main_py = agent_dir / "main.py"
    if not main_py.exists():
        return None
    engine_dir = REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission"
    if not (engine_dir / "cg").is_dir():
        return None
    for p in (str(engine_dir), str(agent_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("candidate_under_test", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_under_test"] = module
    spec.loader.exec_module(module)
    return module


def load_fixture(name):
    """Load captured MAIN-decision obs_dicts. Returns [] when the fixture is absent."""
    path = REPO_ROOT / "data" / "processed" / "instrumentation" / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_profile_knob(m):
    check("profile default is ship",
          m.SEARCH_PROFILE in ("ship", "fast"), f"got {m.SEARCH_PROFILE!r}")
    check("ship profile keeps the 300s game cap",
          m.SEARCH_GAME_TIME_CAP == 300.0, f"got {m.SEARCH_GAME_TIME_CAP}")
    check("determinization count is positive",
          m.PIMC_DETERMINIZATIONS > 0, f"got {m.PIMC_DETERMINIZATIONS}")
    check("per-search time budget is positive",
          m.SEARCH_TIME_BUDGET > 0, f"got {m.SEARCH_TIME_BUDGET}")


def main():
    m = _load_candidate()
    if m is None:
        skip("all", "submissions/archaludon_intent or the cg engine is missing")
    else:
        test_profile_knob(m)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print(f"all passed ({len(SKIPPED)} skipped)")


if __name__ == "__main__":
    main()
