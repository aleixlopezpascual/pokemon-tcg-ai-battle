"""Tests pinning the lucifer19_lossfix_merge (Variant A) grafts and guard restorations.

Run: python3 src/test_lucifer_variants.py

Unlike src/test_lossfix.py, these tests build self-contained mock Observation/PlayerState/
Pokemon objects directly from the real cg.api dataclasses bundled with the submission
(submissions/lucifer19_lossfix_merge/cg/api.py) instead of depending on captured JSON
fixtures -- none are checked in for lucifer19, and captured fixtures are gitignored anyway.
Building real dataclass instances (not ad-hoc SimpleNamespaces) means the field names and
enum values are guaranteed to match what the engine actually sends."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}   {detail}")
        FAILURES.append(name)


def _load_candidate(dirname):
    agent_dir = REPO_ROOT / "submissions" / dirname
    main_py = agent_dir / "main.py"
    if not main_py.exists():
        return None
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    spec = importlib.util.spec_from_file_location(f"{dirname}_under_test", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    m = _load_candidate("lucifer19_lossfix_merge")
    if m is None:
        print("skip: submissions/lucifer19_lossfix_merge/main.py not found")
        return 0

    api = sys.modules["cg.api"]
    Card, Pokemon, PlayerState, State, Observation = (
        api.Card, api.Pokemon, api.PlayerState, api.State, api.Observation,
    )
    Option, SelectData = api.Option, api.SelectData
    AreaType, OptionType, SelectContext, SelectType = (
        api.AreaType, api.OptionType, api.SelectContext, api.SelectType,
    )

    def card(cid, serial=0, player_index=0):
        return Card(id=cid, serial=serial, playerIndex=player_index)

    def pokemon(cid, hp, max_hp=None, energy_cards=None, tools=None, appear_this_turn=False):
        return Pokemon(
            id=cid, serial=0, hp=hp, maxHp=max_hp if max_hp is not None else hp,
            appearThisTurn=appear_this_turn, energies=[],
            energyCards=energy_cards or [], tools=tools or [], preEvolution=[],
        )

    def player(active=None, bench=None, hand=None, prize=None, discard=None, deck_count=40):
        bench = bench or []
        return PlayerState(
            active=[active] if active else [], bench=bench, benchMax=3,
            deckCount=deck_count, discard=discard or [],
            prize=prize if prize is not None else [card(0)] * 6,
            handCount=len(hand) if hand is not None else 0, hand=hand,
            poisoned=False, burned=False, asleep=False, paralyzed=False, confused=False,
        )

    def state(you, opp, your_index=0, supporter_played=False, retreated=False, energy_attached=False):
        players = [None, None]
        players[your_index] = you
        players[1 - your_index] = opp
        return State(
            turn=3, turnActionCount=0, yourIndex=your_index, firstPlayer=0,
            supporterPlayed=supporter_played, stadiumPlayed=False,
            energyAttached=energy_attached, retreated=retreated, result=-1,
            stadium=[], looking=None, players=players,
        )

    def obs(st, select=None):
        return Observation(select=select, logs=[], current=st)

    def select(options, min_count=0, max_count=1, context=None):
        return SelectData(
            type=SelectType.CARD, context=context, minCount=min_count, maxCount=max_count,
            remainDamageCounter=0, remainEnergyCost=0, option=options,
            deck=None, contextCard=None, effect=None,
        )

    METAL = m.METAL_ENERGY
    DURA = m.DURALUDON
    EX = m.ARCHALUDON_EX
    LILLIE = m.LILLIE
    BOSS = m.BOSS
    HERO_CAPE = m.HERO_CAPE
    CRUSTLE = next(iter(m.CRUSTLE_LINE))
    NON_ARCHALUDON = 999999  # never matches any lucifer19/lossfix branch condition

    # ── 1 & 2: _boss_has_lethal gates the Lillie -500 branch ──

    def dura_active(energy=3):
        return pokemon(DURA, hp=130, energy_cards=[card(METAL)] * energy)

    # Test 1: attacker ready, Boss in hand, but remaining prizes (6) exceed any
    # reachable prize_value (max 3) -- no lethal target exists.
    active1 = dura_active()
    opp_bench1 = [pokemon(NON_ARCHALUDON, hp=200)]
    st1 = state(
        you=player(active=active1, hand=[card(BOSS), card(LILLIE)], prize=[card(0)] * 6),
        opp=player(active=pokemon(NON_ARCHALUDON, hp=200), bench=opp_bench1),
    )
    o1 = obs(st1)
    check(
        "_boss_has_lethal False when no bench target clears remaining prizes",
        m._boss_has_lethal(o1) is False,
    )
    lillie_opt1 = Option(type=OptionType.PLAY, index=1)  # hand[1] == LILLIE
    score1, reason1 = m.score_play(o1, lillie_opt1)
    check(
        "Lillie scores 5000 (not saved) when _boss_has_lethal is False",
        score1 == 5000, f"got {score1!r} ({reason1!r})",
    )

    # Test 2: same board, but only 1 prize remains and a bench target with prize_value 1
    # (non-ex) dies to the planned attack -- genuine lethal.
    active2 = dura_active()
    opp_bench2 = [pokemon(NON_ARCHALUDON, hp=50)]  # 80 dmg planned attack KOs this
    st2 = state(
        you=player(active=active2, hand=[card(BOSS), card(LILLIE)], prize=[card(0)] * 1),
        opp=player(active=pokemon(NON_ARCHALUDON, hp=200), bench=opp_bench2),
    )
    o2 = obs(st2)
    check(
        "_boss_has_lethal True on a genuine lethal-bench-target state",
        m._boss_has_lethal(o2) is True,
    )
    lillie_opt2 = Option(type=OptionType.PLAY, index=1)
    score2, reason2 = m.score_play(o2, lillie_opt2)
    check(
        "Lillie scores -500 (saved) when _boss_has_lethal is True",
        score2 == -500, f"got {score2!r} ({reason2!r})",
    )

    # Test 3: no Boss in hand, but a loose Metal Energy is -- Lillie waits for the attach.
    st3 = state(
        you=player(active=None, hand=[card(METAL), card(LILLIE)]),
        opp=player(active=None),
    )
    o3 = obs(st3)
    lillie_opt3 = Option(type=OptionType.PLAY, index=1)
    score3, reason3 = m.score_play(o3, lillie_opt3)
    check(
        "Lillie scores 1500 (save for Metal Energy attach) with no lethal Boss",
        score3 == 1500, f"got {score3!r} ({reason3!r})",
    )

    # ── 4: Crustle bench-attach energy-type gate ──

    def crustle_matchup_state(hand):
        return state(
            you=player(hand=hand, bench=[pokemon(DURA, hp=130)]),
            opp=player(active=pokemon(CRUSTLE, hp=130)),
        )

    st4a = crustle_matchup_state([card(METAL)])
    o4a = obs(st4a, select(options=[], context=SelectContext.MAIN))
    attach_metal_opt = Option(
        type=OptionType.ATTACH, area=AreaType.HAND, index=0,
        inPlayArea=AreaType.BENCH, inPlayIndex=0,
    )
    score4a, reason4a = m.apply_overrides(o4a, attach_metal_opt, 500, "attach Metal")
    check(
        "Crustle +10000 fires for Metal Energy onto benched Duraludon",
        score4a == 10500, f"got {score4a!r} ({reason4a!r})",
    )

    st4b = crustle_matchup_state([card(HERO_CAPE)])
    o4b = obs(st4b, select(options=[], context=SelectContext.MAIN))
    attach_nonmetal_opt = Option(
        type=OptionType.ATTACH, area=AreaType.HAND, index=0,
        inPlayArea=AreaType.BENCH, inPlayIndex=0,
    )
    score4b, reason4b = m.apply_overrides(o4b, attach_nonmetal_opt, 500, "attach Hero's Cape")
    check(
        "Crustle +10000 does NOT fire for a non-Metal card onto benched Duraludon",
        score4b == 500, f"got {score4b!r} ({reason4b!r})",
    )

    # ── 5: Hero's Cape Active-only restriction on Duraludon ──

    st5_bench = state(
        you=player(hand=[card(HERO_CAPE)], bench=[pokemon(DURA, hp=130, energy_cards=[card(METAL)])]),
        opp=player(active=None),
    )
    o5_bench = obs(st5_bench)
    cape_on_bench = Option(
        type=OptionType.ATTACH, area=AreaType.HAND, index=0,
        inPlayArea=AreaType.BENCH, inPlayIndex=0,
    )
    score5a, reason5a = m.score_attach(o5_bench, cape_on_bench)
    check(
        "Hero's Cape onto benched Duraludon is saved (-1000)",
        score5a == -1000, f"got {score5a!r} ({reason5a!r})",
    )

    st5_active = state(
        you=player(active=pokemon(DURA, hp=130, energy_cards=[card(METAL)]), hand=[card(HERO_CAPE)]),
        opp=player(active=None),
    )
    o5_active = obs(st5_active)
    cape_on_active = Option(
        type=OptionType.ATTACH, area=AreaType.HAND, index=0,
        inPlayArea=AreaType.ACTIVE, inPlayIndex=0,
    )
    score5b, reason5b = m.score_attach(o5_active, cape_on_active)
    check(
        "Hero's Cape onto Active Duraludon with energy scores 8000",
        score5b == 8000, f"got {score5b!r} ({reason5b!r})",
    )

    # ── 6: agent()'s crash fallback enforces the minCount floor ──

    st6 = state(you=player(active=None), opp=player(active=None))
    # maxCount (1) deliberately smaller than minCount (2): the pre-graft lucifer19
    # fallback clamped only against maxCount and would under-fill to 1 item here.
    sel6 = select(
        options=[Option(type=OptionType.NUMBER, number=i) for i in range(4)],
        min_count=2, max_count=1,
    )
    o6 = obs(st6, sel6)

    orig_choose_options = m.choose_options
    orig_to_observation_class = m.to_observation_class
    m.choose_options = lambda _obs: (_ for _ in ()).throw(RuntimeError("forced failure"))
    m.to_observation_class = lambda x: x  # obs is already an Observation; skip dict conversion
    try:
        result = m.agent(o6)
    finally:
        m.choose_options = orig_choose_options
        m.to_observation_class = orig_to_observation_class
    check(
        "agent() crash fallback returns exactly min_count items when scorer raises",
        result == [0, 1], f"got {result!r}",
    )

    # ── 7: None-safe all_my_pokemon / detect_matchup ──

    st7 = state(you=player(active=None), opp=player(active=None))
    st7.players[st7.yourIndex].active = None
    st7.players[st7.yourIndex].bench = None
    st7.players[1 - st7.yourIndex].active = None
    st7.players[1 - st7.yourIndex].bench = None
    o7 = obs(st7)
    try:
        my_pokes = m.all_my_pokemon(o7)
        matchup = m.detect_matchup(o7)
        raised = False
    except Exception as e:
        my_pokes, matchup, raised = None, None, e
    check(
        "all_my_pokemon/detect_matchup do not raise when active/bench are None",
        raised is False, f"raised {raised!r}",
    )
    check(
        "all_my_pokemon returns [] when active/bench are None",
        my_pokes == [], f"got {my_pokes!r}",
    )
    check(
        "detect_matchup returns 'generic' when opponent board is None",
        matchup == "generic", f"got {matchup!r}",
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
