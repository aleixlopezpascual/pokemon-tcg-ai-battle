"""Tests for src/label_intent_turns.py's grouping and labeling logic.

Run: python3 src/test_label_intent_turns.py

No episode files or the real candidate module are needed here: `group_into_turns` only touches
plain dict fields (`episode_id`, `player`, `step`, `turn`), and `label_turn` only needs an object
with `INTENTS`, `to_observation_class`, and `choose_options_intent` attributes — a trivial fake
stands in for `submissions/archaludon_intent/main.py` so these tests have no I/O dependency.
"""

import sys

from label_intent_turns import group_into_turns, label_turn

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


def _rec(episode_id, player, step, turn, select=None, current=None, action=None):
    return {
        "episode_id": episode_id, "player": player, "step": step, "turn": turn,
        "select": select if select is not None else {"option": [{}]},
        "current": current if current is not None else {},
        "action": action if action is not None else [0],
    }


def test_group_splits_on_turn_change():
    print("group_into_turns splits on a turn field change")
    records = [
        _rec("ep1", 0, 0, 1),
        _rec("ep1", 0, 1, 1),
        _rec("ep1", 0, 2, 2),
        _rec("ep1", 0, 3, 2),
        _rec("ep1", 0, 4, 3),
    ]
    groups = list(group_into_turns(records))
    turn_numbers = sorted(g[0]["turn"] for _key, g in groups)
    check("three groups produced", len(groups) == 3, f"got {len(groups)}")
    check("turn numbers correct", turn_numbers == [1, 2, 3], f"got {turn_numbers}")

    seen_steps = set()
    for _key, group in groups:
        for r in group:
            seen_steps.add(r["step"])
    check("every input record appears in exactly one group",
          seen_steps == {0, 1, 2, 3, 4}, f"got {seen_steps}")

    total_records_in_groups = sum(len(g) for _key, g in groups)
    check("no record duplicated across groups",
          total_records_in_groups == len(records),
          f"{total_records_in_groups} vs {len(records)}")


def test_group_keeps_different_actors_separate():
    print("group_into_turns keeps different (episode_id, player) keys separate")
    records = [
        _rec("ep1", 0, 0, 3),
        _rec("ep1", 0, 1, 3),
        _rec("ep2", 0, 0, 3),
        _rec("ep2", 0, 1, 3),
        _rec("ep1", 1, 0, 3),
    ]
    groups = list(group_into_turns(records))
    keys = sorted(key for key, _g in groups)
    check("three distinct (episode_id, player) groups",
          keys == [("ep1", 0), ("ep1", 1), ("ep2", 0)], f"got {keys}")
    for key, group in groups:
        check(f"group {key} has all its own records and no other actor's",
              all((r["episode_id"], r["player"]) == key for r in group),
              f"group {key} contents: {group}")


class _FakeSelect:
    def __init__(self, option):
        self.option = option


class _FakeObs:
    def __init__(self, option):
        self.select = _FakeSelect(option)


class _FakeModule:
    """Stands in for submissions/archaludon_intent/main.py for label_turn's needs."""
    INTENTS = ("base", "aggro", "develop")

    @staticmethod
    def to_observation_class(obs_dict):
        select = obs_dict["select"]
        option = select.get("option") if select is not None else None
        return _FakeObs(option)

    @staticmethod
    def choose_options_intent(obs, intent):
        # Deterministic per-intent picks, keyed on the "which_intent" field of the record's
        # select dict, so the test can control exactly which intent "wins" per record.
        picks = obs.select.option[0].get("picks", {})
        return picks.get(intent, [999])  # unknown intent -> guaranteed no-match sentinel


def _rec_for_label(picks, action, has_option=True):
    """A record whose select carries a `picks` map from intent -> predicted action list."""
    option = [{"picks": picks}] if has_option else []
    return {"select": {"option": option}, "current": {}, "action": action}


def test_label_turn_picks_most_matches_tie_broken_by_intents_order():
    print("label_turn picks the max-matches intent, ties broken by INTENTS order")
    m = _FakeModule()
    # Two records: "develop" matches both (unique max), "aggro" matches one, "base" matches none.
    group = [
        _rec_for_label({"base": [1], "aggro": [0], "develop": [0]}, action=[0]),
        _rec_for_label({"base": [1], "aggro": [1], "develop": [0]}, action=[0]),
    ]
    result = label_turn(m, group)
    check("develop wins outright (2/2 matches, strictly more than aggro's 1 and base's 0)",
          result == ("develop", 2, 2), f"got {result}")

    # Now craft an explicit tie between "aggro" and "develop" (both match 1/1), "base" matches 0.
    # INTENTS order is ("base", "aggro", "develop") -> the loop's `matches > best_matches` (strict)
    # means once "aggro" reaches the max, "develop"'s equal score does NOT overwrite it — the
    # first intent (in INTENTS order) to reach the maximum wins.
    tie_group = [
        _rec_for_label({"base": [1], "aggro": [0], "develop": [0]}, action=[0]),
    ]
    tie_result = label_turn(m, tie_group)
    check("tie between aggro and develop is broken in favor of aggro (earlier in INTENTS)",
          tie_result == ("aggro", 1, 1), f"got {tie_result}")


def test_label_turn_no_option_agrees_with_every_intent():
    print("label_turn treats a no-real-decision record as agreeing with every intent")
    m = _FakeModule()
    # One record has no options at all (obs.select.option is empty) -> must count as a match for
    # every intent, not a violation. The other two non-trivially favor "aggro".
    group = [
        _rec_for_label({}, action=[], has_option=False),
        _rec_for_label({"aggro": [0], "develop": [1], "base": [1]}, action=[0]),
        _rec_for_label({"aggro": [0], "develop": [1], "base": [1]}, action=[0]),
    ]
    result = label_turn(m, group)
    check("aggro wins with all 3 matching (1 trivial + 2 real)",
          result == ("aggro", 3, 3), f"got {result}")
    check("the no-option record did not suppress the label (n stayed 3)",
          result[2] == 3, f"got n={result[2]}")


if __name__ == "__main__":
    for fn in (
        test_group_splits_on_turn_change,
        test_group_keeps_different_actors_separate,
        test_label_turn_picks_most_matches_tie_broken_by_intents_order,
        test_label_turn_no_option_agrees_with_every_intent,
    ):
        fn()
        print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print("all passed")
