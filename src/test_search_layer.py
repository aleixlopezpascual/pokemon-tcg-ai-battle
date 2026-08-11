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


def test_generic_policy_scores_real_attack_damage(m):
    """The rollout opponent must rate its own real attacks by their real damage.

    `_generic_score_option`'s ATTACK branch used to call `best_attack_damage`, which only knows
    OUR OWN deck's attacks (`_ATTACK_BASE_DMG` is keyed by our attackIds) and returns 0 for
    everything else -- tying with OptionType.END, also scored 0. That makes the modelled opponent
    treat every non-mirror attack as equally (un)threatening as passing, which flattens PIMC's
    rollouts into a near-passive strawman for every non-Metal deck. Crustle's Superb Scissors
    (attackId 479, real base damage 120, confirmed via cg.api.all_attack()) is a concrete
    non-Archaludon attack the fixture opponent actually has -- it must score well above 0/END.
    """
    check("generic scorer exists", hasattr(m, "_generic_score_option"))
    if not hasattr(m, "_generic_score_option"):
        return

    SUPERB_SCISSORS = 479

    class _Opt:
        def __init__(self, **kw):
            self.type = kw.get("type")
            self.attackId = kw.get("attackId")
            self.number = kw.get("number")
            self.inPlayArea = kw.get("inPlayArea")
            self.cardId = kw.get("cardId")

    class _Sel:
        context = m.SelectContext.ATTACK
        minCount = 1
        maxCount = 1
        option = []

    class _Cur:
        energyAttached = False

    class _Obs:
        select = _Sel()
        current = _Cur()

    obs = _Obs()
    atk = m.ALL_ATTACKS.get(SUPERB_SCISSORS)
    if atk is None:
        skip("generic policy scores real attack damage", "ALL_ATTACKS has no entry for 479 (engine mismatch)")
        return

    attack_score, _ = m._generic_score_option(obs, _Opt(type=m.OptionType.ATTACK, attackId=SUPERB_SCISSORS))
    end_score, _ = m._generic_score_option(obs, _Opt(type=m.OptionType.END))
    check("generic policy scores a real (non-Archaludon) attack above 0/END",
          attack_score > 0 and attack_score > end_score,
          f"Superb Scissors scored {attack_score} vs END {end_score}")
    check("generic policy's attack score matches the engine's real base damage",
          attack_score == atk.damage, f"got {attack_score}, engine says damage={atk.damage}")


def test_intents(m):
    check("INTENTS defined", hasattr(m, "INTENTS"))
    if not hasattr(m, "INTENTS"):
        return
    check("base is the first intent", m.INTENTS[0] == "base", f"got {m.INTENTS}")
    check("five intents", len(m.INTENTS) == 5, f"got {len(m.INTENTS)}")

    fixtures = load_fixture("main_states_crustle.jsonl")
    if not fixtures:
        skip("intents diverge", "no captured MAIN states")
        return

    diverged = 0
    considered = 0
    for obs_dict in fixtures:
        obs = m.to_observation_class(obs_dict)
        if obs.select is None or len(obs.select.option) < 2:
            continue
        considered += 1
        picks = {intent: tuple(m.choose_options_intent(obs, intent)) for intent in m.INTENTS}
        check(f"base intent reproduces choose_options (state {considered})",
              picks["base"] == tuple(m.choose_options(obs)),
              f"{picks['base']} vs {tuple(m.choose_options(obs))}")
        if len(set(picks.values())) > 1:
            diverged += 1
        if considered >= 40:
            break
    if considered:
        share = diverged / considered
        print(f"        (intents diverge on {diverged}/{considered} = {share:.1%} of multi-option states)")
        check("intents diverge somewhere", diverged > 0,
              "every intent picked the same option in every sampled state")


def test_turn_commitment(m):
    check("_committed state exists", hasattr(m, "_committed"))
    if not hasattr(m, "_committed"):
        return
    check("_committed tracks turn and intent",
          set(m._committed) >= {"turn", "intent"}, f"got {sorted(m._committed)}")
    check("_committed defaults to the base intent",
          m._committed["intent"] in m.INTENTS, f"got {m._committed['intent']!r}")
    check("agent() resets the commitment on the deck call",
          "_committed" in m.agent.__code__.co_names
          or "_reset_game_state" in m.agent.__code__.co_names,
          "agent() must clear per-game state including _committed")


def test_fingerprint(m):
    check("_board_fingerprint exists", hasattr(m, "_board_fingerprint"))
    check("_rollout_our_turn_intent exists", hasattr(m, "_rollout_our_turn_intent"))
    if not hasattr(m, "_board_fingerprint"):
        return
    fixtures = load_fixture("main_states_crustle.jsonl")
    if not fixtures:
        skip("fingerprint is stable and hashable", "no captured MAIN states")
        return
    obs = m.to_observation_class(fixtures[0])
    fp1 = m._board_fingerprint(obs)
    fp2 = m._board_fingerprint(obs)
    check("fingerprint is deterministic", fp1 == fp2)
    check("fingerprint is hashable", isinstance(hash(fp1), int))
    distinct = {m._board_fingerprint(m.to_observation_class(f)) for f in fixtures[:40]}
    check("fingerprint distinguishes different boards", len(distinct) > 1,
          f"all {min(40, len(fixtures))} sampled states hashed identically")


def test_intent_classifier_wiring(m):
    if not hasattr(m, "classify_intent"):
        skip("intent classifier wiring", "classify_intent not defined")
        return
    fixtures = load_fixture("main_states_crustle.jsonl")
    if not fixtures:
        skip("intent classifier wiring", "no captured MAIN states")
        return
    checked = 0
    for obs_dict in fixtures:
        obs = m.to_observation_class(obs_dict)
        if obs.select is None or not obs.select.option:
            continue
        intent, probs = m.classify_intent(obs)
        check("classify_intent returns a known intent",
              intent in m.INTENTS, f"got {intent!r}")
        check("classify_intent probs sum to ~1",
              abs(sum(probs) - 1.0) < 1e-6, f"sum={sum(probs)}")
        check("classify_intent probs length matches classes",
              len(probs) == len(m._INTENT_CLASSES), f"{len(probs)} vs {len(m._INTENT_CLASSES)}")
        checked += 1
        if checked >= 10:
            break
    print(f"        ({checked} states checked)")


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
        test_generic_policy_scores_real_attack_damage(m)
        test_intents(m)
        test_turn_commitment(m)
        test_fingerprint(m)
        test_intent_classifier_wiring(m)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print(f"all passed ({len(SKIPPED)} skipped)")


if __name__ == "__main__":
    main()
