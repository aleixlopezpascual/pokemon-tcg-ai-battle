"""Tests pinning submissions/archaludon_lossfix/main.py's base-heuristic fixes.

Run: python3 src/test_lossfix.py

Each fix gets a captured-obs fixture (a single MAIN-decision obs_dict, saved as JSON under
data/processed/instrumentation/lossfix_fixtures/<name>.json) and a before/after assertion on
score_option's or a named sub-scorer's return value. Skips cleanly when the candidate or a
fixture is absent (both are gitignored)."""

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


def _load_candidate(dirname="archaludon_lossfix"):
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
    spec = importlib.util.spec_from_file_location("lossfix_under_test", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lossfix_under_test"] = module
    spec.loader.exec_module(module)
    return module


def load_fixture(name):
    path = REPO_ROOT / "data" / "processed" / "instrumentation" / "lossfix_fixtures" / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def main():
    m = _load_candidate()
    if m is None:
        skip("all lossfix tests", "submissions/archaludon_lossfix not present locally")
    else:
        run_all_tests(m)
    print(f"\n{len(FAILURES)} failed, {len(SKIPPED)} skipped")
    if FAILURES:
        sys.exit(1)


def run_all_tests(m):
    pass  # each fix sub-step below appends one test_<fix_name>(m) call here


if __name__ == "__main__":
    main()
