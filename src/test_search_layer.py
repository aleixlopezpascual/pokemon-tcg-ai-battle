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


def test_classify_returns_name(m):
    """_classify_opponent_archetype must report WHICH archetype matched, not just the decklist."""
    fixtures = load_fixture("main_states_crustle.jsonl")
    if not fixtures:
        skip("classify returns archetype name", "no captured MAIN states")
        return
    named = 0
    for obs_dict in fixtures:
        obs = m.to_observation_class(obs_dict)
        result = m._classify_opponent_archetype(obs)
        check("classify returns a 3-tuple", len(result) == 3, f"got {len(result)}")
        deck, seen, name = result
        if deck is not None:
            check("matched deck comes with a name", isinstance(name, str), f"got {name!r}")
            check("name is a known archetype",
                  name in m._ARCHETYPE_DECKS, f"got {name!r}")
            named += 1
        else:
            check("unmatched deck reports no name", name is None, f"got {name!r}")
        break  # one state is enough to pin the contract
    print(f"        ({named} of 1 sampled states matched an archetype)")


def test_rank_options(m):
    fixtures = load_fixture("main_states_crustle.jsonl")
    if not fixtures:
        skip("rank_options", "no captured MAIN states")
        return
    checked = 0
    for obs_dict in fixtures:
        obs = m.to_observation_class(obs_dict)
        if obs.select is None or not obs.select.option:
            continue
        ranked = m.rank_options(obs)
        idxs = [i for _, i, _ in ranked]
        check("rank_options is a permutation of all option indices",
              sorted(idxs) == list(range(len(obs.select.option))),
              f"{sorted(idxs)} vs {list(range(len(obs.select.option)))}")
        scores = [s for s, _, _ in ranked]
        check("rank_options is sorted best-first",
              scores == sorted(scores, reverse=True), f"{scores}")
        if obs.select.maxCount == 1:
            check("rank_options head agrees with choose_options",
                  m.choose_options(obs)[0] == idxs[0],
                  f"{m.choose_options(obs)} vs {idxs[:1]}")
        checked += 1
        if checked >= 25:
            break
    print(f"        ({checked} states checked)")


def test_shared_determinization(m):
    fixtures = load_fixture("main_states_crustle.jsonl")
    if not fixtures:
        skip("shared determinization", "no captured MAIN states")
        return
    import inspect
    sig = inspect.signature(m._search_begin_determinized)
    check("_search_begin_determinized accepts a precomputed kwargs dict",
          "kwargs" in sig.parameters, f"got {list(sig.parameters)}")
    check("_pimc_score_lines exists", hasattr(m, "_pimc_score_lines"))
    check("PIMC_MARGIN is set above zero", getattr(m, "PIMC_MARGIN", 0) > 0,
          f"got {getattr(m, 'PIMC_MARGIN', None)}")

    obs = None
    for obs_dict in fixtures:
        o = m.to_observation_class(obs_dict)
        if o.select is not None and o.select.option:
            obs = o
            break
    if obs is None:
        skip("determinization is resampled", "no usable MAIN state")
        return
    deck = m.read_deck_csv()
    draws = [m._hidden_info_kwargs(obs, deck) for _ in range(6)]
    hands = [tuple(d["opponent_hand"]) for d in draws]
    check("hidden-info draws differ across resamples",
          len(set(hands)) > 1 or all(len(h) == 0 for h in hands),
          f"all {len(hands)} draws identical: {hands[0]}")
    check("every draw has the same zone sizes",
          len({(len(d["opponent_deck"]), len(d["opponent_hand"]),
                len(d["opponent_prize"])) for d in draws}) == 1)


def test_generic_policy_attaches_energy(m):
    """The rollout opponent must be able to attach non-Metal energy.

    score_attach returns (-500, "skip non-Metal") for every card id other than METAL_ENERGY=8,
    and END scores 0, so the Archaludon policy models every non-Metal opponent as a player who
    never powers up. That makes non-mirror rollouts unwinnable for the opponent and destroys
    PIMC's discrimination.
    """
    check("generic scorer exists", hasattr(m, "_generic_score_option"))
    check("generic chooser exists", hasattr(m, "_generic_choose_options"))
    if not hasattr(m, "_generic_score_option"):
        return

    class _Opt:
        def __init__(self, **kw):
            self.type = kw.get("type")
            self.attackId = kw.get("attackId")
            self.number = kw.get("number")
            self.inPlayArea = kw.get("inPlayArea")
            self.cardId = kw.get("cardId")

    class _Sel:
        context = m.SelectContext.MAIN
        minCount = 1
        maxCount = 1
        option = []

    class _Cur:
        energyAttached = False

    class _Obs:
        select = _Sel()
        current = _Cur()

    obs = _Obs()
    attach_score, _ = m._generic_score_option(obs, _Opt(type=m.OptionType.ATTACH))
    end_score, _ = m._generic_score_option(obs, _Opt(type=m.OptionType.END))
    check("generic policy prefers attaching energy over ending the turn",
          attach_score > end_score, f"attach {attach_score} vs end {end_score}")

    evolve_score, _ = m._generic_score_option(obs, _Opt(type=m.OptionType.EVOLVE))
    check("generic policy prefers evolving over ending the turn",
          evolve_score > end_score, f"evolve {evolve_score} vs end {end_score}")


def main():
    m = _load_candidate()
    if m is None:
        skip("all", "submissions/archaludon_intent or the cg engine is missing")
    else:
        test_profile_knob(m)
        test_classify_returns_name(m)
        test_rank_options(m)
        test_shared_determinization(m)
        test_generic_policy_attaches_energy(m)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print(f"all passed ({len(SKIPPED)} skipped)")


if __name__ == "__main__":
    main()
