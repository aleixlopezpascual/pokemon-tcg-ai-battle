"""Tests for the PIMC Common-Random-Numbers fix in submissions/archaludon_search/main.py.

Run: python3 src/test_pimc_crn.py

Regression test for the 2026-08-13 audit finding: pre-fix, `_pimc_score` resampled its own
opponent worlds independently per candidate (via `_search_begin_determinized` inside the
scoring loop), so between-candidate variance was dominated by which worlds got sampled, not
by which action was better -- override rate 0.8%. This pins the fix: worlds are generated
once per decision (`_generate_pimc_worlds`) and every candidate is scored against the same
set, `_pimc_score` takes those worlds as an explicit argument, and the candidate loop in
`search_reorder` gives every candidate an equal budget slice with no base-first tie bias.

The candidate lives in a gitignored directory (needs its local `cg/` copy), so every test
skips cleanly when the candidate or engine is absent.
"""

import importlib.util
import inspect
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


def _load_candidate(dirname="archaludon_search"):
    agent_dir = REPO_ROOT / "submissions" / dirname
    main_py = agent_dir / "main.py"
    cg_dir = agent_dir / "cg"
    if not main_py.exists() or not cg_dir.is_dir():
        return None
    for p in (str(agent_dir),):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("candidate_under_test", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_generate_pimc_worlds_signature(m):
    check("_generate_pimc_worlds exists", hasattr(m, "_generate_pimc_worlds"))
    if not hasattr(m, "_generate_pimc_worlds"):
        return
    sig = inspect.signature(m._generate_pimc_worlds)
    check("_generate_pimc_worlds takes (obs, my_deck, k)",
          list(sig.parameters) == ["obs", "my_deck", "k"], f"got {list(sig.parameters)}")


def test_pimc_score_takes_worlds(m):
    check("_pimc_score exists", hasattr(m, "_pimc_score"))
    if not hasattr(m, "_pimc_score"):
        return
    sig = inspect.signature(m._pimc_score)
    params = list(sig.parameters)
    check("_pimc_score's last parameter is worlds (CRN, shared across candidates)",
          params and params[-1] == "worlds", f"got {params}")


def _fake_obs(m, my_deck):
    """Minimal fake matching the attribute chain _hidden_info_kwargs/_classify_opponent_archetype
    walk: obs.current.players[i].{prize, deckCount, handCount, active, bench, discard}."""

    class _Player:
        def __init__(self):
            self.prize = [None, None, None, None, None, None]
            self.deckCount = 10
            self.handCount = 3
            self.active = [None]
            self.bench = []
            self.discard = []

    class _Current:
        def __init__(self):
            self.yourIndex = 0
            self.players = [_Player(), _Player()]

    class _Obs:
        def __init__(self):
            self.current = _Current()

    return _Obs()


def test_worlds_are_cacheable_data(m):
    """`_generate_pimc_worlds`'s output must be a plain list of dicts (data), not live state --
    that is what makes reusing the same worlds across every candidate in a decision safe."""
    check("_hidden_info_kwargs exists", hasattr(m, "_hidden_info_kwargs"))
    check("_generate_pimc_worlds exists", hasattr(m, "_generate_pimc_worlds"))
    if not (hasattr(m, "_hidden_info_kwargs") and hasattr(m, "_generate_pimc_worlds")):
        return
    my_deck = m.read_deck_csv()
    obs = _fake_obs(m, my_deck)
    worlds = m._generate_pimc_worlds(obs, my_deck, 5)
    check("_generate_pimc_worlds returns k worlds", len(worlds) == 5, f"got {len(worlds)}")
    check("every world is a plain dict", all(isinstance(w, dict) for w in worlds),
          f"types: {[type(w) for w in worlds]}")


def test_generate_pimc_worlds_restores_random_state(m):
    """Seeding `random` per world index must not leak into unrelated random.sample() fallbacks
    used elsewhere in this file -- the fix seeds/restores getstate()/setstate() around the loop."""
    import random
    check("_generate_pimc_worlds exists", hasattr(m, "_generate_pimc_worlds"))
    if not hasattr(m, "_generate_pimc_worlds"):
        return
    my_deck = m.read_deck_csv()
    obs = _fake_obs(m, my_deck)
    random.seed(12345)
    state_before = random.getstate()
    m._generate_pimc_worlds(obs, my_deck, 5)
    state_after = random.getstate()
    check("random state is restored after generating worlds",
          state_before == state_after,
          "random.getstate() differs before/after _generate_pimc_worlds")


def test_no_privileged_base_on_ties(m):
    """search_reorder's candidate loop must track best_scored and prefer the candidate that
    completed more worlds on a tie, not whichever came first in `candidates` (the old bug:
    base_selected[0] is always candidates[0], so a bare `>` comparison kept it on every tie)."""
    src = inspect.getsource(m.search_reorder)
    check("candidate loop tracks a scored-world count (best_scored)",
          "best_scored" in src, "search_reorder has no best_scored tracking")
    check("tie-break compares scored-world counts, not candidate position",
          "n_scored > best_scored" in src, "no n_scored > best_scored tie-break found")


def test_per_candidate_budget_slice(m):
    """Each PIMC candidate must get its own deadline slice of the remaining budget, not share
    one deadline that lets the first-scored (base) candidate spend freely and starve the rest."""
    src = inspect.getsource(m.search_reorder)
    check("candidate loop computes a per-candidate slice_deadline",
          "slice_deadline" in src, "no slice_deadline found in search_reorder")
    check("slice sizing divides the remaining pimc_budget across n_candidates",
          "pimc_budget / n_candidates" in src,
          "budget is not divided evenly across candidates")


def test_override_rate_gate_documented(m):
    """The gate this fix must clear: override rate (changed/pimc_decisions) in [10%, 40%].
    This test only checks the counters exist and are internally consistent after a run is
    simulated at zero games -- the actual rate is measured by src/search_telemetry.py-style
    battle runs (see notebooks/kaggle-research/10-day-plan.md's 2026-08-13 entry: 21.3%,
    46/216, measured PASS), not reproduced here since it needs real battles."""
    check("_search_stats tracks pimc_decisions", "pimc_decisions" in m._search_stats)
    check("_search_stats tracks changed", "changed" in m._search_stats)
    check("counters start at zero on a fresh import",
          m._search_stats["pimc_decisions"] == 0 and m._search_stats["changed"] == 0,
          f"got {m._search_stats}")


def main():
    m = _load_candidate()
    if m is None:
        skip("all", "submissions/archaludon_search or its local cg/ is missing")
    else:
        test_generate_pimc_worlds_signature(m)
        test_pimc_score_takes_worlds(m)
        test_worlds_are_cacheable_data(m)
        test_generate_pimc_worlds_restores_random_state(m)
        test_no_privileged_base_on_ties(m)
        test_per_candidate_budget_slice(m)
        test_override_rate_gate_documented(m)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print(f"all passed ({len(SKIPPED)} skipped)")


if __name__ == "__main__":
    main()
