"""Archaludon ex + Cinderace — Rule-based agent (Public version)

Deck Concept:
  Cinderace's Explosiveness places it face-down as Active during setup.
  Turn 1 Turbo Flare ({C}=50) accelerates up to 3 Basic Energy from deck
  to benched Duraludon. Evolving into Archaludon ex triggers Assemble Alloy,
  attaching up to 2 Basic Metal Energy from discard to Metal Pokemon.
  Metal Defender ({M}{M}{M}=220) is the main attack; no Weakness next turn.
  Duraludon can attack directly with Raging Hammer ({M}{M}{C}=80 + 10 per
  damage counter) without evolving. Relicanth's Memory Dive also unlocks
  Raging Hammer on Archaludon ex after evolution. Hero's Cape gives +100 HP
  (HP400). Full Metal Lab reduces attack damage to Metal Pokemon by 30.

Pokemon:
  Duraludon (169)      - Basic Metal HP130. Hammer In {M}=30.
                         Raging Hammer {M}{M}{C}=80+10*damage_counters.
  Archaludon ex (190)  - Stage 1 from Duraludon, HP300. Assemble Alloy: on evolve
                         from hand, attach up to 2 Metal Energy from discard.
                         Metal Defender {M}{M}{M}=220, no Weakness next turn.
  Cinderace (666)      - Stage 2 HP160. Explosiveness: place face-down as Active
                         in setup from opening hand. Turbo Flare {C}=50, attach
                         up to 3 Basic Energy from deck to benched Pokemon.
  Relicanth (57)       - Basic HP100. Memory Dive: evolved Pokemon can use attacks
                         from previous Evolutions. Archaludon ex -> Raging Hammer.

Trainers:
  Poke Pad (1152), Ultra Ball (1121), Pokegear 3.0 (1122), Night Stretcher (1097),
  Jumbo Ice Cream (1147), Hero's Cape (1159), Boss's Orders (1182),
  Explorer's Guidance (1185), Lillie's Determination (1227), Full Metal Lab (1244) x4.

Energy: Basic Metal Energy (8) x11

Score system:
  Setup/play/evolve/attach: 1000~28000 (high = do first)
  Attack: damage value (always last — attacking ends the turn)
  Negative = skip if above minCount
"""

import os
import random
import sys
import time
from collections import Counter

try:
    ROOT = __file__
except NameError:
    ROOT = None
CG_PATH = "/kaggle_simulations/agent"
for p in ([os.path.dirname(os.path.abspath(ROOT))] if ROOT else []) + [CG_PATH]:
    if p and p not in sys.path and os.path.isdir(p):
        sys.path.insert(0, p)

from cg.api import (
    AreaType,
    CardType,
    LogType,
    OptionType,
    SelectContext,
    all_card_data,
    to_observation_class,
)

try:
    from cg.api import all_attack
    ALL_ATTACKS = {a.attackId: a for a in all_attack()}
except Exception:
    ALL_ATTACKS = {}

# ── Card IDs ──

DURALUDON = 169
ARCHALUDON_EX = 190
CINDERACE = 666
RELICANTH = 57
CRUSTLE_LINE = {344, 345, 532}
STARMIE_LINE = {1030, 1031}
LUCARIO_LINE = {677, 678}
HOP_LINE = {288, 289, 299, 304, 307, 308, 309, 310, 878, 879}
HOP_SNORLAX = 304

METAL_ENERGY = 8

POKE_PAD = 1152
ULTRA_BALL = 1121
POKEGEAR = 1122
NIGHT_STRETCHER = 1097
JUMBO_ICE_CREAM = 1147
HERO_CAPE = 1159
BOSS = 1182
EXPLORER = 1185
LILLIE = 1227
FULL_METAL_LAB = 1244

RAGING_HAMMER = 224
METAL_DEFENDER = 253

_ATTACK_BASE_DMG = {METAL_DEFENDER: 220, 965: 50, 223: 30, 61: 30}

_SETUP_ACTIVE_PRIORITY = {
    CINDERACE: (100000, "Active: Cinderace Explosiveness"),
    DURALUDON: (20000, "Active fallback: Duraludon"),
    RELICANTH: (5000, "Active fallback: Relicanth"),
}

ALWAYS_SAFE_DISCARD = {METAL_ENERGY, CINDERACE}

CARD_DB = {c.cardId: c for c in all_card_data()}

MEGA_BRAVE = 983
PREMIUM_POWER_PRO = 1141
HARIYAMA_LINE = {673, 674}

# Track opponent's last-turn attack via logs
_opp_last_attack_id = None
_cur_turn_logs = []


def _update_opp_attack_tracking(obs):
    global _opp_last_attack_id, _cur_turn_logs
    yi = obs.current.yourIndex
    for entry in obs.logs:
        if entry.type == LogType.TURN_END:
            for prev in _cur_turn_logs:
                if prev.type == LogType.ATTACK and getattr(prev, 'playerIndex', yi) != yi:
                    _opp_last_attack_id = prev.attackId
            _cur_turn_logs.clear()
        else:
            _cur_turn_logs.append(entry)


# ── Board helpers ──

def read_deck_csv():
    fp = "deck.csv"
    if not os.path.exists(fp):
        fp = "/kaggle_simulations/agent/deck.csv"  # real Kaggle sandbox path
    if not os.path.exists(fp):
        # Local test harnesses (run_battle.py, ladder_eval.py) load main.py via importlib from an
        # arbitrary cwd, so neither path above resolves -- this was previously masked because the
        # only caller was inside search_reorder's own try/except, silently degrading search to a
        # permanent no-op locally rather than surfacing the missing fallback. Real Kaggle `exec()`s
        # this file with no __file__ (see CLAUDE.md's exec()-without-__file__ gotcha), hence the
        # try/except NameError -- but __file__ is exactly what importlib-based local loading
        # provides, so this branch is what makes search actually exercisable outside Kaggle.
        try:
            fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deck.csv")
        except NameError:
            pass
    with open(fp) as f:
        return [int(line) for line in f.read().strip().split("\n")]


def get_card(obs, area, index, player_index):
    if area is None or index is None:
        return None
    ps = obs.current.players[player_index]
    if area == AreaType.DECK and obs.select and obs.select.deck is not None:
        return obs.select.deck[index] if index < len(obs.select.deck) else None
    if area == AreaType.HAND and ps.hand is not None:
        return ps.hand[index] if index < len(ps.hand) else None
    if area == AreaType.DISCARD:
        return ps.discard[index] if index < len(ps.discard) else None
    if area == AreaType.ACTIVE:
        return ps.active[index] if index < len(ps.active) else None
    if area == AreaType.BENCH:
        return ps.bench[index] if index < len(ps.bench) else None
    if area == AreaType.PRIZE:
        return ps.prize[index] if index < len(ps.prize) else None
    if area == AreaType.STADIUM:
        return obs.current.stadium[index] if index < len(obs.current.stadium) else None
    if area == AreaType.LOOKING and obs.current.looking is not None:
        return obs.current.looking[index] if index < len(obs.current.looking) else None
    return None


def option_card(obs, opt):
    yi = obs.current.yourIndex
    pi = opt.playerIndex if opt.playerIndex is not None else yi
    if opt.type == OptionType.PLAY:
        return get_card(obs, AreaType.HAND, opt.index, pi)
    return get_card(obs, opt.area, opt.index, pi)


def option_target(obs, opt):
    if opt.inPlayArea is None or opt.inPlayIndex is None:
        return None
    return get_card(obs, opt.inPlayArea, opt.inPlayIndex, obs.current.yourIndex)


def my_state(obs):
    return obs.current.players[obs.current.yourIndex]


def opp_state(obs):
    return obs.current.players[1 - obs.current.yourIndex]


def active_pokemon(obs):
    ps = my_state(obs)
    return ps.active[0] if ps.active else None


def opp_active_pokemon(obs):
    ps = opp_state(obs)
    return ps.active[0] if ps.active else None


def opp_bench_pokemon(obs):
    return [p for p in opp_state(obs).bench if p]


def all_my_pokemon(obs):
    ps = my_state(obs)
    return [p for p in ((ps.active or []) + (ps.bench or [])) if p]


def hand_ids(obs):
    hand = my_state(obs).hand
    return [c.id for c in hand if c] if hand else []


def discard_ids(obs):
    return [c.id for c in (my_state(obs).discard or []) if c]


def metal_in_discard(obs):
    return sum(1 for c in (my_state(obs).discard or []) if c and c.id == METAL_ENERGY)


def energy_count(pokemon):
    if pokemon is None:
        return 0
    if getattr(pokemon, "energyCards", None) is not None:
        return len(pokemon.energyCards)
    return len(getattr(pokemon, "energies", []) or [])


def retreat_cost(pokemon):
    data = CARD_DB.get(pokemon.id) if pokemon else None
    return getattr(data, "retreatCost", 0) if data else 0


def damage_on(pokemon):
    if pokemon is None:
        return 0
    return max(0, getattr(pokemon, "maxHp", pokemon.hp) - pokemon.hp)


def has_tool(pokemon):
    return bool(getattr(pokemon, "tools", []) or [])


def count_in_play(obs, card_id):
    return sum(1 for p in all_my_pokemon(obs) if p.id == card_id)


def has_in_play(obs, card_id):
    return any(p.id == card_id for p in all_my_pokemon(obs))


def need_duraludon(obs):
    return sum(1 for p in all_my_pokemon(obs) if p.id in {DURALUDON, ARCHALUDON_EX}) < 2


def need_archaludon(obs):
    has_dura, ex_count = False, 0
    for p in all_my_pokemon(obs):
        if p.id == DURALUDON:
            has_dura = True
        elif p.id == ARCHALUDON_EX:
            ex_count += 1
    return has_dura and ex_count < 2


def safe_discard_count(obs):
    ids = hand_ids(obs)
    mt = metal_in_discard(obs)
    safe = 0
    for cid in ids:
        if cid == METAL_ENERGY and mt + safe < 2:
            safe += 1
        elif cid == CINDERACE:
            safe += 1
    draw_in_hand = sum(1 for c in ids if c in (LILLIE, EXPLORER))
    if draw_in_hand >= 2:
        safe += draw_in_hand - 1
    return safe


def prize_value(pokemon):
    data = CARD_DB.get(pokemon.id) if pokemon else None
    if data and getattr(data, "megaEx", False):
        return 3
    if data and getattr(data, "ex", False):
        return 2
    return 1


def best_attack_damage(obs, attack_id):
    if attack_id == RAGING_HAMMER:
        return 80 + damage_on(active_pokemon(obs)) // 10 * 10
    return _ATTACK_BASE_DMG.get(attack_id, 0)


def is_metal_weak(pokemon):
    if pokemon is None:
        return False
    data = CARD_DB.get(pokemon.id)
    w = getattr(data, "weakness", None) if data else None
    if w is None:
        return False
    return getattr(w, "value", w) == METAL_ENERGY


def effective_damage(base_damage, target):
    return base_damage * 2 if is_metal_weak(target) else base_damage


def _first_option_index(obs, card_id):
    for o in obs.select.option:
        oc = option_card(obs, o)
        if oc and oc.id == card_id:
            return getattr(o, 'index', None)
    return None


# ── Attack routes ──

def direct_attack_energy_route(obs, pokemon):
    e = energy_count(pokemon)
    if e >= 3:
        return True, False
    if e == 2 and not obs.current.energyAttached and METAL_ENERGY in hand_ids(obs):
        return True, True
    return False, False


def can_evolve_to_archaludon_now(pokemon, obs):
    if pokemon is None or pokemon.id != DURALUDON:
        return False
    if ARCHALUDON_EX not in hand_ids(obs):
        return False
    return not getattr(pokemon, "appearThisTurn", True)


def alloy_attack_energy_route(obs, pokemon):
    if not can_evolve_to_archaludon_now(pokemon, obs):
        return False, False
    current = energy_count(pokemon)
    alloy = min(2, metal_in_discard(obs))
    total = current + alloy
    if total >= 3:
        return True, False
    if total == 2 and not obs.current.energyAttached and METAL_ENERGY in hand_ids(obs):
        return True, True
    return False, False


def attack_energy_route(obs, pokemon):
    if pokemon is None:
        return False, False
    if pokemon.id == ARCHALUDON_EX:
        return direct_attack_energy_route(obs, pokemon)
    if pokemon.id == DURALUDON:
        ok, uses_attach = direct_attack_energy_route(obs, pokemon)
        if ok:
            return True, uses_attach
        return alloy_attack_energy_route(obs, pokemon)
    return False, False


def archaludon_ex_attack_route(obs):
    active = active_pokemon(obs)
    if active and active.id in {ARCHALUDON_EX, DURALUDON}:
        ok, uses_attach = attack_energy_route(obs, active)
        if ok:
            return {"attacker": active, "uses_attach": uses_attach, "needs_retreat": False}

    if active is None or obs.current.retreated or energy_count(active) < retreat_cost(active):
        return None
    ps = my_state(obs)
    for pokemon in [p for p in ps.bench if p]:
        if pokemon.id not in {ARCHALUDON_EX, DURALUDON}:
            continue
        ok, uses_attach = attack_energy_route(obs, pokemon)
        if ok:
            return {"attacker": pokemon, "uses_attach": uses_attach, "needs_retreat": True}
    return None


def planned_archaludon_attacks(obs):
    route = archaludon_ex_attack_route(obs)
    if route is None:
        return []
    attacker = route["attacker"]
    attacks = []
    if attacker.id == ARCHALUDON_EX:
        attacks.append({"damage": 220})
        if has_in_play(obs, RELICANTH):
            attacks.append({"damage": 80 + damage_on(attacker) // 10 * 10})
    if attacker.id == DURALUDON:
        attacks.append({"damage": 80 + damage_on(attacker) // 10 * 10})
        if can_evolve_to_archaludon_now(attacker, obs):
            attacks.append({"damage": 220})
    return attacks


# ── Matchup detection & opponent max damage ──

ALAKAZAM_LINE = {741, 742, 743}
_ALA_BOARD_GAIN = {66: 3, 742: 2, 305: 2, 65: 2, 741: 1}  # Dudunsparce, Kadabra, Dunsparce×2, Abra


def _estimate_alakazam_from_pokes(opp, pokes):
    """(floor, ceiling, ceiling_with_boss) damage from visible Alakazam line."""
    ids = [p.id for p in pokes if p]
    if not (ALAKAZAM_LINE & set(ids)):
        return 0, 0, 0
    base = opp.handCount + 1
    gain = sum(_ALA_BOARD_GAIN.get(i, 0) for i in ids)
    enriching_seen = (
        any(c and c.id == 13 for c in (opp.discard or []))
        or any(c and c.id == 13 for p in pokes if p for c in (getattr(p, "energyCards", None) or []))
    )
    if not enriching_seen:
        gain += 3
    if any(i == 140 for i in ids):
        gain += 3
    return base * 20, (base + gain + 2) * 20, (base + gain - 1) * 20


def _estimate_alakazam(obs):
    """(floor, ceiling, ceiling_with_boss) damage from Powerful Hand."""
    opp = opp_state(obs)
    pokes = ([opp.active[0]] if opp.active else []) + list(opp.bench or [])
    return _estimate_alakazam_from_pokes(opp, pokes)


def detect_matchup(obs):
    opp = opp_state(obs)
    ids = {p.id for p in ((opp.active or []) + (opp.bench or [])) if p}
    if ids & CRUSTLE_LINE:
        return "crustle"
    if ids & HOP_LINE:
        return "hop"
    if ids & STARMIE_LINE:
        return "starmie"
    if ids & LUCARIO_LINE:
        return "lucario"
    if ids & ALAKAZAM_LINE:
        return "alakazam"
    return "generic"


def opp_max_damage(obs):
    matchup = detect_matchup(obs)
    if matchup == "alakazam":
        _, ceiling, _ = _estimate_alakazam(obs)
        return ceiling
    if matchup == "crustle":
        return 120
    if matchup == "hop":
        return 220
    if matchup == "lucario":
        return 270  # Mega Brave base. PPP adds +30 each but unpredictable
    if matchup == "starmie":
        return 210
    return 220


# ── Overrides ──

def apply_overrides(obs, opt, score, reason):
    # Hard rule: don't Explorer with low deck
    if opt.type == OptionType.PLAY:
        card = option_card(obs, opt)
        cid = card.id if card else None
        if my_state(obs).deckCount <= 10 and cid == EXPLORER:
            return -5000, "hard: don't Explorer with low deck"

    if detect_matchup(obs) != "crustle":
        return score, reason

    # Crustle overrides
    card = option_card(obs, opt)
    cid = card.id if card else getattr(opt, 'cardId', None)
    ctx = obs.select.context

    if opt.type == OptionType.EVOLVE and cid == ARCHALUDON_EX:
        return -10000, "Crustle: don't evolve to ex"

    if opt.type == OptionType.ATTACK:
        aid = getattr(opt, 'attackId', None)
        active = active_pokemon(obs)
        opp_act = opp_active_pokemon(obs)
        opp_has_spiky = bool(opp_act and any(
            getattr(c, 'id', None) == 14
            for c in (getattr(opp_act, 'energyCards', None) or [])))
        if (active and active.id == DURALUDON and active.hp == 130
                and opp_act and opp_act.id == 345 and energy_count(opp_act) >= 2
                and opp_has_spiky):
            return -3000, "Crustle: full HP Duraludon waits out Spiky"
        if aid == METAL_DEFENDER:
            return -5000, "Crustle: Metal Defender does 0"
        if aid == RAGING_HAMMER:
            rh_dmg = 80 + damage_on(active_pokemon(obs)) // 10 * 10
            return max(score, 200), "Crustle: Raging Hammer"

    if opt.type == OptionType.PLAY:
        if cid == RELICANTH:
            return -5000, "Crustle: skip Relicanth"
        dc = my_state(obs).deckCount
        if dc <= 10 and cid in (EXPLORER, LILLIE):
            if cid == LILLIE and dc <= 3 and my_state(obs).handCount >= dc + 6:
                return 15000, "Crustle: Lillie to refill deck"
            return -5000, "Crustle: don't draw with low deck"
        if cid == LILLIE:
            has_metal = any(c and c.id == METAL_ENERGY for c in (my_state(obs).hand or []) if c)
            if not has_metal:
                return score, "Crustle: Lillie OK (no energy in hand)"

    if opt.type == OptionType.ATTACH:
        target = option_target(obs, opt)
        tid = target.id if target else None
        if getattr(opt, 'inPlayArea', None) == AreaType.BENCH and tid == DURALUDON:
            return score + 10000, "Crustle: bench Duraludon energy priority"
        if getattr(opt, 'inPlayArea', None) == AreaType.ACTIVE:
            active = active_pokemon(obs)
            if active and energy_count(active) >= 2:
                return score + 3000, "Crustle: Active 3rd energy"

    if ctx == SelectContext.TO_HAND and opt.type == OptionType.CARD and cid == ARCHALUDON_EX:
        return -3000, "Crustle: skip Archaludon ex"

    if ctx in {SelectContext.DISCARD, SelectContext.DISCARD_CARD_OR_ATTACHED_CARD}:
        if cid == ARCHALUDON_EX and score < 0:
            return 9000, "Crustle: discard Archaludon ex"

    return score, reason


# ── Scoring ──

def score_setup(obs, opt):
    card = option_card(obs, opt)
    cid = card.id if card else None
    ctx = obs.select.context

    if ctx == SelectContext.MULLIGAN:
        return (10000, "no mulligan") if opt.type == OptionType.NO else (0, "mulligan")
    if ctx == SelectContext.IS_FIRST:
        return (10000, "choose second") if opt.type == OptionType.NO else (0, "go first")
    if ctx == SelectContext.SETUP_ACTIVE_POKEMON:
        return _SETUP_ACTIVE_PRIORITY.get(cid, (0, "unknown Active"))
    if ctx == SelectContext.SETUP_BENCH_POKEMON:
        return -10000, "never bench during setup"
    return 0, "non-setup"


# HP threshold per matchup: skip Ice Cream if HP > this value
_ICE_CREAM_HP_THRESHOLD = {
    "lucario": 270,
    "starmie": 210,
    "crustle": 120,
    "hop": 220,
    "generic": 230,
}


def should_skip_ice_cream(obs, active):
    """Decide whether to skip Jumbo Ice Cream. Returns (skip: bool, reason: str)."""
    # 1. Active must be Archaludon ex
    if active.id != ARCHALUDON_EX:
        return True, "skip Ice Cream: not Archaludon ex"
    # 2. Raging Hammer KO guard: don't heal if it loses a KO (but 220 Metal Defender still KOs → heal OK)
    opp_act = opp_active_pokemon(obs)
    if opp_act and has_in_play(obs, RELICANTH):
        md_kills = effective_damage(220, opp_act) >= opp_act.hp
        if not md_kills:
            rh_dmg = 80 + damage_on(active) // 10 * 10
            rh_after = 80 + max(0, damage_on(active) - 80) // 10 * 10
            if effective_damage(rh_dmg, opp_act) >= opp_act.hp and effective_damage(rh_after, opp_act) < opp_act.hp:
                return True, "skip Ice Cream: healing loses Raging Hammer KO"
    # 3. Alakazam: all-or-nothing Ice Cream decision
    matchup = detect_matchup(obs)
    if matchup == "alakazam":
        floor, ceiling, _ = _estimate_alakazam(obs)
        opp_a = opp_active_pokemon(obs)
        attacks = planned_archaludon_attacks(obs)
        if opp_a and attacks and any(effective_damage(a["damage"], opp_a) >= opp_a.hp for a in attacks):
            _, ceiling, _ = _estimate_alakazam_from_pokes(opp_state(obs), opp_bench_pokemon(obs))
        ice_count = sum(1 for c in (my_state(obs).hand or []) if c and c.id == JUMBO_ICE_CREAM)
        max_hp = getattr(active, "maxHp", active.hp)
        hp_after_all = min(max_hp, active.hp + ice_count * 80)
        if hp_after_all <= active.hp:
            return True, "skip Ice Cream: no effective healing"
        if hp_after_all < floor:
            return True, f"skip Ice Cream: even {ice_count}x heal ({hp_after_all}) < floor {floor}"
        if hp_after_all >= ceiling:
            return False, f"use Ice Cream: {ice_count}x heal ({hp_after_all}) >= ceil {ceiling}"
        return False, f"use Ice Cream: {ice_count}x heal ({hp_after_all}) between floor={floor} ceil={ceiling}"
    # 4. HP above matchup threshold
    threshold = _ICE_CREAM_HP_THRESHOLD.get(matchup, 220)
    if active.hp > threshold:
        return True, f"skip Ice Cream: HP {active.hp} > {threshold} ({matchup})"
    # 5. Use it
    return False, ""


ITEMS = {POKE_PAD, ULTRA_BALL, POKEGEAR, NIGHT_STRETCHER, JUMBO_ICE_CREAM, HERO_CAPE}


def score_play(obs, opt):
    card = option_card(obs, opt)
    cid = card.id if card else None
    ids = hand_ids(obs)

    # ── Pokemon: bench if available ──
    if cid in {DURALUDON, RELICANTH}:
        return 18000, "play Pokemon"

    # ── Stadium ──
    if cid == FULL_METAL_LAB:
        active = active_pokemon(obs)
        if active and active.id not in {DURALUDON, ARCHALUDON_EX}:
            return -200, "skip FML: Active not Metal"
        return 20000, "play Full Metal Lab"

    # ── Items: default 20000, only negative exceptions ──
    if cid in ITEMS:
        if cid == HERO_CAPE:
            if not any(p.id in {ARCHALUDON_EX, DURALUDON} and not has_tool(p) for p in all_my_pokemon(obs)):
                return -500, "save Hero's Cape: no target"
        if cid == JUMBO_ICE_CREAM:
            active = active_pokemon(obs)
            if active:
                skip, reason = should_skip_ice_cream(obs, active)
                if skip:
                    return -500, reason
        if cid == NIGHT_STRETCHER:
            disc = discard_ids(obs)
            has_urgent = (
                (DURALUDON in disc and DURALUDON not in ids and count_in_play(obs, DURALUDON) + count_in_play(obs, ARCHALUDON_EX) <= 1)
                or (ARCHALUDON_EX in disc and ARCHALUDON_EX not in ids and has_in_play(obs, DURALUDON))
                or (METAL_ENERGY in disc and not obs.current.energyAttached
                    and sum(1 for c in (my_state(obs).hand or []) if c and c.id == METAL_ENERGY) == 0
                    and any(p and p.id in (DURALUDON, ARCHALUDON_EX) and energy_count(p) == 2 for p in all_my_pokemon(obs)))
            )
            if not has_urgent:
                return -500, "save Night Stretcher"
        if cid == ULTRA_BALL:
            bench_empty = len([p for p in my_state(obs).bench if p]) == 0
            if bench_empty:
                return 300, "Ultra Ball: bench empty (donk risk)"
            metal_in_hand = sum(1 for c in (my_state(obs).hand or []) if c and c.id == METAL_ENERGY)
            metal_in_trash = metal_in_discard(obs)
            if metal_in_trash == 0 and metal_in_hand >= 1:
                return 20000, "Ultra Ball: fuel Alloy"
            if safe_discard_count(obs) >= 2 and (need_archaludon(obs) or need_duraludon(obs)):
                return 20000, "Ultra Ball: search line"
            return -1000, "skip Ultra Ball"
        return 20000, "play item"

    if cid == EXPLORER:
        if obs.current.supporterPlayed:
            return -1000, "Supporter already used"
        return 16000, "play Explorer"

    if cid == LILLIE:
        if obs.current.supporterPlayed:
            return -1000, "Supporter already used"
        if BOSS in ids and planned_archaludon_attacks(obs):
            return -500, "save Lillie: Boss in hand with attacker ready"
        return 5000, "play Lillie"

    if cid == BOSS:
        if obs.current.supporterPlayed:
            return -1000, "Supporter already used"
        # vs Hop: Boss Snorlax to remove Extra Helpings (+30) ASAP
        if detect_matchup(obs) == "hop":
            active = active_pokemon(obs)
            opp_has_snorlax = any(p.id == HOP_SNORLAX for p in opp_bench_pokemon(obs))
            if opp_has_snorlax and active:
                # Case 1: Cinderace active + bench has Duraludon → Turbo Flare Snorlax
                if active.id == CINDERACE:
                    has_dura_bench = any(p.id in {DURALUDON, ARCHALUDON_EX}
                                        for p in my_state(obs).bench if p)
                    if has_dura_bench:
                        return 16500, "Boss: pull Snorlax (Cinderace Turbo Flare)"
                # Case 2: Archaludon active, HP > 220, can attack → Boss Snorlax
                if active.id == ARCHALUDON_EX and active.hp > 220:
                    ok, _ = attack_energy_route(obs, active)
                    if ok:
                        return 16500, "Boss: pull Snorlax (Arch can tank Revenge 220)"
        if _opp_last_attack_id == MEGA_BRAVE:
            return -500, "save Boss: Mega Brave stuck"
        attacks = planned_archaludon_attacks(obs)
        if not attacks:
            return -500, "save Boss: no attacker"
        opp_act = opp_active_pokemon(obs)
        can_ko_active = opp_act and any(
            effective_damage(atk["damage"], opp_act) >= opp_act.hp for atk in attacks)
        remaining = len(my_state(obs).prize)
        if can_ko_active:
            if prize_value(opp_act) >= remaining:
                return -500, "save Boss: Active KO wins"
            for target in opp_bench_pokemon(obs):
                for atk in attacks:
                    if effective_damage(atk["damage"], target) >= target.hp:
                        if prize_value(target) >= remaining:
                            return 20000, "LETHAL Boss"
                        break
            return -500, "save Boss: can KO Active"
        best_score = -500
        best_reason = "save Boss"
        for target in opp_bench_pokemon(obs):
            for atk in attacks:
                if effective_damage(atk["damage"], target) >= target.hp:
                    pv = prize_value(target)
                    if pv >= remaining:
                        return 20000, "LETHAL Boss"
                    s = 4000 + pv * 200 + energy_count(target) * 100
                    if s > best_score:
                        best_score = s
                        best_reason = "Boss: pull bench target"
                    break
        if best_score <= 0:
            metal_total = sum(1 for c in (my_state(obs).hand or []) if c and c.id == METAL_ENERGY)
            metal_total += sum(energy_count(p) for p in all_my_pokemon(obs) if p)
            has_cind = has_in_play(obs, CINDERACE)
            draw_in_hand = any(c and c.id in (EXPLORER, LILLIE) for c in (my_state(obs).hand or []) if c)
            if metal_total <= 2 and not has_cind and not draw_in_hand:
                best_stall = -500
                stall_reason = "save Boss"
                for target in opp_bench_pokemon(obs):
                    te = energy_count(target)
                    cd = CARD_DB.get(target.id)
                    rc = cd.retreatCost if cd else 0
                    min_atk = 99
                    if cd and cd.attacks:
                        for aid in cd.attacks:
                            atk = ALL_ATTACKS.get(aid)
                            if atk:
                                min_atk = min(min_atk, len(atk.energies))
                    if min_atk == 99:
                        min_atk = 1
                    ss = 4000 + rc * 1000 + min_atk * 500 - te * 800
                    if ss > best_stall:
                        best_stall = ss
                        stall_reason = "Boss stall"
                return best_stall, stall_reason
        return best_score, best_reason

    return 1000, "generic play"


def score_evolve(obs, opt):
    card = option_card(obs, opt)
    target = option_target(obs, opt)
    cid = card.id if card else None
    tid = target.id if target else None
    if cid == ARCHALUDON_EX and tid == DURALUDON:
        target_is_active = opt.inPlayArea == AreaType.ACTIVE
        mc = metal_in_discard(obs)
        if target_is_active:
            if energy_count(target) >= 3 and not has_in_play(obs, ARCHALUDON_EX):
                return 17000, "evolve Active 3-energy Duraludon"
            if mc >= 2:
                return 28000 + mc * 2000, "evolve Active Duraludon"
            if mc == 1:
                return 8000, "delay Active evolve: 1 Metal"
            return -500, "hold: no Metal in discard"
        if mc >= 2:
            return 14000 + mc * 1000, "evolve Bench Duraludon"
        return -1000, "hold: evolve Active first"
    return 10000, "generic evolution"


def attach_target_score(obs, target, area):
    if target is None:
        return 0
    cid = target.id
    e = energy_count(target)

    if e >= 3:
        return -5000
    if cid == CINDERACE and e >= 1:
        return -3000

    score = 0
    if cid == CINDERACE:
        score = 3000
        if e == 0:
            score += 7000 + (12000 if area == AreaType.ACTIVE else 5000)
    elif cid in {DURALUDON, ARCHALUDON_EX}:
        score = 6000 if cid == ARCHALUDON_EX else 5500
        score += {2: 12000, 1: 7000, 0: 4000}.get(e, -1000)
        score += 1000 if area == AreaType.ACTIVE else 500
    else:
        score = 1000 + (1000 if e == 0 else 0)

    # HP-based adjustment
    if target.hp > 0:
        max_hp = getattr(target, "maxHp", target.hp)
        ratio = target.hp / max_hp if max_hp > 0 else 1
        if ratio <= 0.25:
            score -= 1500
        elif ratio <= 0.50:
            score -= 500
        else:
            score += min(1000, target.hp // 40 * 100)
    return score


def score_attach(obs, opt):
    card = option_card(obs, opt)
    target = option_target(obs, opt)
    cid = card.id if card else None
    tid = target.id if target else None

    if cid == HERO_CAPE:
        if tid == ARCHALUDON_EX and target and not has_tool(target):
            return 11000, "Hero's Cape on Archaludon ex"
        if tid == DURALUDON and target and not has_tool(target) and energy_count(target) >= 1:
            return 8000, "Hero's Cape on Duraludon"
        return -1000, "save Hero's Cape"

    if cid != METAL_ENERGY:
        return -500, "skip non-Metal"
    if obs.current.energyAttached:
        return -1000, "already attached"

    return attach_target_score(obs, target, opt.inPlayArea), "attach Metal"


def score_retreat(obs, opt):
    active = active_pokemon(obs)
    if active and active.id == ARCHALUDON_EX and has_tool(active) and active.hp > 200:
        return -5000, "don't retreat HP400 tank"
    route = archaludon_ex_attack_route(obs)
    if route and route["needs_retreat"]:
        return 13000, "retreat to attack-ready ex"
    return -100, "avoid retreat"


_MAIN_DISPATCH = {
    OptionType.PLAY: score_play, OptionType.EVOLVE: score_evolve,
    OptionType.ATTACH: score_attach, OptionType.RETREAT: score_retreat,
}


def score_option(obs, opt):
    ctx = obs.select.context

    if ctx in {SelectContext.IS_FIRST, SelectContext.MULLIGAN,
               SelectContext.SETUP_ACTIVE_POKEMON, SelectContext.SETUP_BENCH_POKEMON}:
        return score_setup(obs, opt)

    if opt.type in {OptionType.YES, OptionType.NO}:
        if ctx == SelectContext.IS_FIRST:
            return score_setup(obs, opt)
        if ctx == SelectContext.ACTIVATE:
            return (100000, "Explosiveness") if opt.type == OptionType.YES else (-100000, "never decline")
        return (1, "yes") if opt.type == OptionType.YES else (0, "no")

    if opt.type == OptionType.NUMBER:
        return (opt.number or 0), "number"

    if ctx == SelectContext.MAIN:
        fn = _MAIN_DISPATCH.get(opt.type)
        if fn:
            score, reason = fn(obs, opt)
        elif opt.type == OptionType.ABILITY:
            score, reason = 1, "ability"
        elif opt.type == OptionType.ATTACK:
            score, reason = best_attack_damage(obs, opt.attackId), "attack"
        elif opt.type == OptionType.END:
            score, reason = 0, "end turn"
        else:
            score, reason = 500, "generic MAIN"
    elif ctx == SelectContext.TO_HAND:
        score, reason = score_to_hand(obs, opt)
    elif ctx in {SelectContext.DISCARD, SelectContext.DISCARD_CARD_OR_ATTACHED_CARD}:
        score, reason = score_discard(obs, opt)
    elif ctx in {SelectContext.ATTACH_TO, SelectContext.TO_FIELD, SelectContext.TO_BENCH,
                 SelectContext.ATTACH_FROM, SelectContext.SWITCH, SelectContext.TO_ACTIVE,
                 SelectContext.HEAL, SelectContext.DAMAGE}:
        score, reason = score_target(obs, opt)
    elif ctx == SelectContext.ATTACK:
        score, reason = best_attack_damage(obs, opt.attackId), "attack"
    elif opt.type == OptionType.CARD:
        score, reason = score_to_hand(obs, opt)
    elif opt.type == OptionType.ENERGY:
        score, reason = 1000, "energy"
    elif opt.type == OptionType.END:
        score, reason = 0, "end"
    else:
        score, reason = 100, "fallback"

    return apply_overrides(obs, opt, score, reason)


def score_to_hand(obs, opt):
    card = option_card(obs, opt)
    cid = card.id if card else opt.cardId
    ids = hand_ids(obs)
    effect = getattr(obs.select, "effect", None)
    effect_id = effect.id if effect else None

    if effect_id == EXPLORER:
        has_ready = any(p and p.id in (DURALUDON, ARCHALUDON_EX) and energy_count(p) >= 3
                        for p in all_my_pokemon(obs))
        metal_in_hand = sum(1 for c in (my_state(obs).hand or []) if c and c.id == METAL_ENERGY)

        if cid == HERO_CAPE:
            has_target = any(p.id == ARCHALUDON_EX and not has_tool(p) for p in all_my_pokemon(obs))
            return (27000 if has_target else 22000), "Explorer: Hero's Cape"
        if cid == METAL_ENERGY:
            if has_ready or metal_in_hand > 0:
                return 0, "Explorer: skip energy"
            if getattr(opt, 'index', 0) == _first_option_index(obs, METAL_ENERGY):
                return 25000, "Explorer: take 1st energy"
            return 0, "Explorer: skip 2nd energy"
        if cid == ARCHALUDON_EX and need_archaludon(obs):
            return 20000, "Explorer: take Archaludon ex"
        if cid == DURALUDON and need_duraludon(obs):
            return 18000, "Explorer: take Duraludon"
        if cid == RELICANTH and not has_in_play(obs, RELICANTH) and RELICANTH not in ids:
            return 15000, "Explorer: take Relicanth"
        sup_count = sum(1 for c in (my_state(obs).hand or []) if c and c.id in (EXPLORER, LILLIE))
        if cid in (EXPLORER, LILLIE) and sup_count == 0:
            return 12000, "Explorer: take supporter"
        return 0, "Explorer: let discard"

    dura_ex_count = count_in_play(obs, DURALUDON) + count_in_play(obs, ARCHALUDON_EX)
    if cid == DURALUDON and DURALUDON not in ids and dura_ex_count <= 1:
        return 22000, "take Duraludon: backup"
    if cid == ARCHALUDON_EX and need_archaludon(obs):
        return 20000, "take Archaludon ex"
    if cid == DURALUDON and need_duraludon(obs):
        return 18000, "take Duraludon"
    if cid == CINDERACE:
        return -2000, "skip Cinderace"
    if cid == RELICANTH and not has_in_play(obs, RELICANTH):
        return 9000, "take Relicanth"
    if cid == METAL_ENERGY:
        return 8000, "take Metal Energy"
    if cid == EXPLORER and not obs.current.supporterPlayed:
        return 7500, "take Explorer"
    if cid == LILLIE and not obs.current.supporterPlayed:
        return 6500, "take Lillie"
    if cid == HERO_CAPE:
        has_target = any(p.id == ARCHALUDON_EX and not has_tool(p) for p in all_my_pokemon(obs))
        return (6000, "take Hero's Cape") if has_target else (1000, "generic take")
    if cid == FULL_METAL_LAB:
        return 5000, "take Full Metal Lab"
    if cid == BOSS:
        return 2500, "take Boss"
    return 1000, "generic take"


def score_discard(obs, opt):
    card = option_card(obs, opt)
    cid = card.id if card else opt.cardId
    ids = hand_ids(obs)
    mt = metal_in_discard(obs)
    effect = getattr(obs.select, "effect", None)
    effect_id = effect.id if effect else None

    if effect_id == ULTRA_BALL:
        mh = ids.count(METAL_ENERGY)
        if cid == METAL_ENERGY:
            if mt < 2 and mh >= 1:
                if getattr(opt, 'index', None) == _first_option_index(obs, METAL_ENERGY):
                    return 20000, "UB: 1st Metal"
                return 8000, "UB: 2nd Metal"
            return 8000, "UB: Metal"
        if cid == CINDERACE:
            return (18000, "UB: Cinderace") if (mt >= 2 or mh == 0) else (14000, "UB: Cinderace")
        draw_count = ids.count(LILLIE) + ids.count(EXPLORER)
        if cid in (LILLIE, EXPLORER) and draw_count >= 2:
            return (12000 if cid == LILLIE else 11000), "UB: surplus supporter"
        if cid == ULTRA_BALL and ids.count(ULTRA_BALL) > 1:
            return 10000, "UB: duplicate"
        if cid in (LILLIE, EXPLORER) and draw_count <= 1:
            return -3000, "UB: keep last supporter"

    if cid == METAL_ENERGY:
        if mt < 2:
            return 15000, "discard Metal"
        return (12000, "discard extra Metal") if ids.count(METAL_ENERGY) > 1 else (-1000, "keep last Metal")
    if cid == CINDERACE:
        return 10000, "discard Cinderace"
    if cid in {BOSS, FULL_METAL_LAB, POKEGEAR}:
        return 8500, "discard utility"
    if cid in {LILLIE, EXPLORER} and ids.count(cid) > 1:
        return 8000, "discard duplicate supporter"
    if cid == RELICANTH and (has_in_play(obs, RELICANTH) or ids.count(RELICANTH) > 1):
        return 6500, "discard extra Relicanth"
    if cid == ARCHALUDON_EX:
        return -5000, "keep Archaludon ex"
    if cid == DURALUDON:
        return -4000, "keep Duraludon"
    return 1000, "generic discard"


def score_target(obs, opt):
    card = option_card(obs, opt)
    cid = card.id if card else opt.cardId
    ctx = obs.select.context

    if ctx == SelectContext.ATTACH_TO:
        return (5000, "Metal") if cid == METAL_ENERGY else (1000, "attach")

    if ctx == SelectContext.ATTACH_FROM:
        if card and energy_count(card) >= 3:
            return -5000, "skip: 3+ energy"
        if card and cid == CINDERACE and energy_count(card) >= 1:
            return -3000, "skip: Cinderace ready"
        return attach_target_score(obs, card, opt.area), "effect attach"

    if ctx in {SelectContext.TO_FIELD, SelectContext.TO_BENCH}:
        if cid == ARCHALUDON_EX:
            return 18000, "target Archaludon ex"
        if cid == DURALUDON:
            return 16000, "target Duraludon"
        if cid == CINDERACE:
            return 3000, "avoid Cinderace"

    if ctx == SelectContext.HEAL:
        return (20000 + damage_on(card), "heal Archaludon ex") if cid == ARCHALUDON_EX else (damage_on(card), "heal")

    if ctx in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
        yi = obs.current.yourIndex
        pi = getattr(opt, 'playerIndex', yi)
        if pi != yi and card:
            # vs Hop: prioritize Snorlax (remove Extra Helpings)
            if detect_matchup(obs) == "hop" and cid == HOP_SNORLAX and card:
                active = active_pokemon(obs)
                e = energy_count(card)
                tools = len(getattr(card, 'tools', None) or [])
                if active and active.id == CINDERACE:
                    # Cinderace: pull the least mobile Snorlax (low energy, no tools, high HP)
                    return 30000 - e * 100 - tools * 50 + card.hp, "Boss: Snorlax (immobile target)"
                else:
                    # Archaludon: pull the most threatening Snorlax (high energy, tools, high HP)
                    return 30000 + e * 100 + tools * 50 + card.hp, "Boss: Snorlax (biggest threat)"
            pv = prize_value(card)
            te = energy_count(card)
            killable = any(effective_damage(a["damage"], card) >= card.hp
                           for a in planned_archaludon_attacks(obs))
            if killable:
                return 20000 + pv * 3000 + te * 100, "Boss: KO"
            return 5000 + pv * 1000 + te * 200, "Boss: drag"
        if cid == CINDERACE:
            return 16000, "promote Cinderace (retreat 0)"
        if cid == ARCHALUDON_EX:
            return 15000, "promote Archaludon ex"
        if cid == DURALUDON:
            return 8000, "promote Duraludon"
        return 1000, "generic promote"

    if ctx == SelectContext.DAMAGE:
        hp = getattr(card, "hp", 999) if card else 999
        return 10000 - hp, "damage: lowest HP"

    return 1000, "generic target"


# ── Choose & Agent ──

def choose_options(obs):
    scored = []
    for i, opt in enumerate(obs.select.option):
        try:
            score, reason = score_option(obs, opt)
        except Exception as e:
            score, reason = -999999, f"error {type(e).__name__}: {e}"
        scored.append((score, i, reason))

    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)

    selected = []
    for score, i, reason in scored:
        if len(selected) >= obs.select.maxCount:
            break
        if score < 0 and len(selected) >= obs.select.minCount:
            continue
        selected.append(i)

    if len(selected) < obs.select.minCount:
        selected = [i for _, i, _ in scored[:obs.select.minCount]]

    return selected


def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        global _opp_last_attack_id, _cur_turn_logs, _game_search_seconds
        _opp_last_attack_id = None
        _cur_turn_logs.clear()
        _game_search_seconds = 0.0
        return read_deck_csv()
    _update_opp_attack_tracking(obs)
    if not obs.select.option:
        return []
    try:
        return search_reorder(obs, choose_options(obs))
    except Exception:
        n_options = len(obs.select.option)
        k = max(obs.select.minCount, min(obs.select.maxCount, n_options))
        return random.sample(list(range(n_options)), k) if k > 0 else []


# ---------------------------------------------------------------------------
# Forward-search layer
# ---------------------------------------------------------------------------
#
# The engine exposes a real forward simulator (`search_begin` / `search_step`) and this agent has
# never used it. Measured cost on this hardware: 0.19 ms per `search_begin`, 0.13 ms per
# `search_step`, against a host budget of 600 s per game and about 51 MAIN decisions per battle
# for one side. Roughly 11 s per decision is available; we spend single-digit milliseconds.
#
# What the layer does, and why this scope:
#
# The base scorer ranks options one at a time from hand-written heuristics. It never sees the
# board that an option actually produces. Search does: for each candidate first action we replay
# the rest of our own turn with the base policy and evaluate the *resulting* board. The choice is
# then made on consequences rather than on a guess about consequences.
#
# The obvious narrower scope -- lethal detection -- was built first and measured, and it does not
# pay. Over 150 battles the search found a winning line 253 times but overrode the base policy
# only 9 times (0.20% of MAIN decisions): in 244 of 253 cases the heuristic had already ranked the
# winning move first. Lethal is kept below as a free fast path, not as the mechanism.
#
# 2026-08-10 revision: the two limits named above are addressed rather than just documented.
#
# Opponent hidden information used to be our own decklist cycled -- "wrong nearly always" by the
# original author's own admission -- which is why the evaluator was scoped to our own side only.
# It is now a guess against the real field: classify the opponent's revealed cards against known
# meta decklists (the same ones `src/ladder_eval.py`'s panel is drawn from) and fill the hidden
# zones from the best match, shuffled fresh per determinization. Still a guess, but one grounded
# in what other real submissions actually play, not a guess that is structurally always wrong.
#
# With a plausible opponent, a full-game rollout is worth taking: `evaluate_board`'s hand-picked
# prize/damage weights are gone, replaced by PIMC (Perfect Information Monte Carlo) -- roll both
# sides forward with the base policy as a stand-in to a real terminal result, resample the guessed
# hidden information each draw, and score by actual win rate. This cannot repeat the earlier
# evaluator's 4%/8%/0% failure because it has no invented weights left to get wrong.
#
# manual_coin=True makes coin flips inside these rollouts choosable instead of unmodelled engine
# randomness. Answered pessimistically for us (see `_pick_coin`) rather than left to whatever
# `choose_options`' generic YES/NO fallback would have picked -- that fallback was never designed
# to answer a coin toss and manual coin flips never reach it outside of search.
#
# Everything still fails closed: any error, any budget overrun, and the base policy's answer
# stands. A per-game time bank (`_game_search_seconds` / `SEARCH_GAME_TIME_CAP`) adds a second
# ceiling above the per-decision one, so a slow host cannot let ~50 decisions each spend right up
# to their own cap and blow the 600 s game budget in aggregate.

_SEARCH_OK = False
try:
    from cg.api import search_begin, search_release, search_step
    _SEARCH_OK = True
except Exception:  # pragma: no cover - cg is always present in the sandbox
    pass

SEARCH_MODE = "pimc"      # "off" | "lethal" | "veto" | "pimc"
SEARCH_TIME_BUDGET = 5.0     # seconds of wall clock per MAIN decision, hard ceiling
SEARCH_MAX_CANDIDATES = 8    # first actions to try, taken in base-policy order
SEARCH_MAX_PLIES = 24        # steps of our own turn to roll forward before giving up
SEARCH_MAX_TOTAL_PLIES = 80  # steps of the WHOLE rollout (both sides) before giving up on a draw
PIMC_DETERMINIZATIONS = 20   # resampled opponent hidden-info draws averaged per candidate action
SEARCH_GAME_TIME_CAP = 300.0  # cumulative search seconds per game; half the 600s host budget

_search_stats = {
    "calls": 0, "began": 0, "lethal": 0, "changed": 0, "budget": 0, "errors": 0,
    "vetoed": 0, "game_capped": 0, "pimc_playouts": 0, "pimc_decisions": 0,
    "archetype_matched": 0,
}

_game_search_seconds = 0.0


# ── Opponent determinization ──
#
# Our version of the reachability tensor: one derived-state object -- "which real 60-card list is
# this opponent most likely playing" -- that both the hidden-info fill and the active-Pokemon
# guess read from, instead of each inventing its own placeholder.
#
# Card IDs are hardcoded rather than read from `submissions/*/deck.csv` because only this agent's
# own `deck.csv` ships inside its tarball; the other submissions' files are local-repo-only. These
# are the exact 60-card lists of every candidate that has been real-scored or audited on the
# ladder so far, i.e. the same field `src/ladder_eval.py`'s panel is drawn from.
_ARCHETYPE_DECKS = {
    "dragapult_ex": [
        119, 119, 119, 119, 120, 120, 120, 120, 121, 121, 121, 140, 184, 235, 235, 1071,
        1079, 1079, 1080, 1086, 1086, 1086, 1086, 1097, 1097, 1120, 1120, 1120, 1120, 1121,
        1121, 1121, 1121, 1152, 1152, 1152, 1156, 1182, 1182, 1182, 1198, 1198, 1198, 1198,
        1210, 1210, 1227, 1227, 1227, 1227, 1256, 1256, 2, 2, 2, 2, 5, 5, 5, 5,
    ],
    "libraryout_crustle": [
        58, 58, 58, 58, 344, 344, 344, 344, 345, 345, 1142, 1142, 1142, 1142, 1152, 1152,
        1152, 1152, 1086, 1086, 1086, 1086, 1122, 1122, 1122, 1122, 1121, 1123, 1123, 1123,
        1123, 1197, 1197, 1197, 1197, 1185, 1185, 1185, 1185, 1182, 1182, 1182, 1182, 1204,
        1204, 1194, 1194, 1247, 1147, 20, 20, 20, 20, 11, 11, 11, 11, 345, 345, 607,
    ],
    "mega_lucario_ex": [
        673, 673, 674, 674, 675, 675, 676, 676, 676, 677, 677, 677, 678, 678, 678, 678,
        1102, 1102, 1102, 1102, 1123, 1123, 1141, 1141, 1141, 1141, 1142, 1142, 1142, 1142,
        1152, 1152, 1152, 1152, 1159, 1182, 1182, 1192, 1192, 1192, 1192, 1227, 1227, 1227,
        1227, 1252, 1252, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    ],
    "alakazam_dunsparce": [
        5, 5, 5, 13, 19, 19, 19, 19, 66, 66, 66, 305, 305, 305, 305, 741, 741, 741, 741,
        742, 742, 742, 742, 743, 743, 743, 743, 1079, 1079, 1079, 1079, 1081, 1081, 1081,
        1081, 1086, 1086, 1086, 1086, 1097, 1097, 1097, 1129, 1152, 1152, 1152, 1152, 1182,
        1182, 1182, 1184, 1225, 1225, 1225, 1225, 1231, 1231, 1231, 1231, 1264,
    ],
    "probablity_v2": [
        673, 673, 674, 674, 675, 675, 676, 676, 676, 677, 677, 677, 678, 678, 678, 678,
        1102, 1102, 1102, 1102, 1123, 1123, 1141, 1141, 1141, 1141, 1142, 1142, 1142, 1142,
        1152, 1152, 6, 1159, 1182, 1182, 1192, 1192, 1192, 1192, 1227, 1227, 1227, 1227, 6,
        6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 1182, 677, 1252,
    ],
    "archaludon_cinderace": [
        169, 169, 169, 169, 190, 190, 190, 190, 666, 666, 666, 666, 1244, 57, 1152, 1152,
        1152, 1152, 1121, 1121, 1121, 1121, 1122, 1122, 1122, 1122, 1097, 1097, 1097, 1147,
        1147, 1147, 1147, 1159, 1182, 1182, 1182, 1182, 1185, 1185, 1185, 1185, 1227, 1227,
        1227, 1227, 1244, 1244, 1244, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,
    ],
}


def _archetype_active_guess(deck_ids):
    """Guess a plausible starting Active for an archetype: its cheapest-retreat Basic Pokemon.

    Real decks usually lead a low-retreat-cost Basic (Duraludon/Dragapult-line starters and the
    like), and this only needs to be plausible enough for `search_begin`'s count validation to
    accept it -- it is overwritten by the real, visible active as soon as one exists.
    """
    basics = sorted(
        {cid for cid in deck_ids if (CARD_DB.get(cid) and CARD_DB[cid].cardType == CardType.POKEMON
                                      and CARD_DB[cid].basic)},
        key=lambda cid: getattr(CARD_DB[cid], "retreatCost", 99),
    )
    return basics[0] if basics else None


def _classify_opponent_archetype(obs):
    """Match the opponent's revealed cards against `_ARCHETYPE_DECKS`. Returns (deck_or_None, seen_ids).

    Only active/bench/discard are ever visible for the opponent (`PlayerState.hand` is `None` for
    them) -- this never peeks at anything the real game hides. Overlap is scored by
    `min(times_seen, times_in_deck)` per card so seeing one copy of a 4-of can't outscore seeing a
    single distinctive tech card; a minimum score is required before trusting a match over the
    always-legal mirror-cycling fallback, since a handful of generic Basic Energy is not evidence.
    """
    op = opp_state(obs)
    seen = []
    for p in (op.active or []) + (op.bench or []):
        if p is not None:
            seen.append(p.id)
    for c in (op.discard or []):
        if c is not None:
            seen.append(c.id)
    if not seen:
        return None, []

    seen_counts = Counter(seen)
    best_name, best_deck, best_score = None, None, 0
    for name, deck in _ARCHETYPE_DECKS.items():
        deck_counts = Counter(deck)
        score = sum(min(n, deck_counts.get(cid, 0)) for cid, n in seen_counts.items())
        if score > best_score:
            best_name, best_deck, best_score = name, deck, score

    if best_score < 2:
        return None, seen
    return best_deck, seen


def _pick_coin(obs, my_index):
    """Answer a manual COIN_HEAD select pessimistically for `my_index`.

    Manual coin flips never occur outside search (`manual_coin=False` in every real game), so
    `choose_options`/`score_option` has no branch for one and was never meant to answer one. Which
    side of a flip is good depends on the specific attack/ability text, which this layer does not
    parse -- rather than guess, it is consistently pessimistic: deny ourselves heads on our own
    flip, grant the opponent heads on theirs. Whatever heads happens to mean here, PIMC's win rate
    then already prices in the coin's worst case instead of hiding it as unmodelled noise.
    """
    acting_is_us = obs.current.yourIndex == my_index
    want_no = acting_is_us  # our flip: answer NO (deny heads); their flip: answer YES (grant it)
    for i, opt in enumerate(obs.select.option):
        if (opt.type == OptionType.NO) == want_no:
            return [i]
    return [0]


def _hidden_info_kwargs(obs, my_deck):
    """Fill `search_begin`'s hidden zones with legal IDs, guessed from the real meta where possible.

    The engine validates counts, not correctness. When the opponent's revealed cards match a
    known archetype (`_classify_opponent_archetype`), the fill draws from that archetype's actual
    60-card list minus the cards already seen, shuffled fresh -- callers that invoke this
    repeatedly (once per PIMC determinization) get a different plausible hand/deck/prize split
    each time. Falls back to cycling our own decklist, the original always-wrong placeholder,
    only when no archetype scores well enough to trust.
    """
    cur = obs.current
    me = cur.players[cur.yourIndex]
    op = cur.players[1 - cur.yourIndex]

    def cycle_fill(pool, n):
        return [pool[i % len(pool)] for i in range(n)] if n > 0 and pool else []

    d_n = getattr(op, "deckCount", 0)
    h_n = getattr(op, "handCount", 0)
    p_n = len(op.prize)

    archetype_deck, seen = _classify_opponent_archetype(obs)
    if archetype_deck is not None:
        _search_stats["archetype_matched"] += 1
        remaining = list(archetype_deck)
        for cid in seen:
            if cid in remaining:
                remaining.remove(cid)
        random.shuffle(remaining)
        needed = d_n + h_n + p_n
        if len(remaining) < needed:
            remaining = remaining + cycle_fill(archetype_deck, needed - len(remaining))
        opponent_deck = remaining[:d_n]
        opponent_hand = remaining[d_n:d_n + h_n]
        opponent_prize = remaining[d_n + h_n:d_n + h_n + p_n]
        active_guess = _archetype_active_guess(archetype_deck) or DURALUDON
    else:
        opponent_deck = cycle_fill(my_deck, d_n)
        opponent_hand = cycle_fill(my_deck, h_n)
        opponent_prize = cycle_fill(my_deck, p_n)
        active_guess = DURALUDON

    op_active = op.active
    # Required only when the opponent's active is face-down, and it must be a Pokemon ID.
    needs_active = len(op_active) > 0 and op_active[0] is None
    return {
        "your_deck": list(my_deck),
        "your_prize": cycle_fill(my_deck, len(me.prize)),
        "opponent_deck": opponent_deck,
        "opponent_prize": opponent_prize,
        "opponent_hand": opponent_hand,
        "opponent_active": [active_guess] if needs_active else [],
    }


def _search_begin_determinized(obs, my_deck):
    """`search_begin` with a freshly resampled opponent guess and coin flips made choosable.

    A thin wrapper so every caller that starts a new determinization (the lethal/veto fast paths,
    and each of PIMC's resampled draws) gets both pieces of Task 2/4 together rather than one
    call site remembering `manual_coin=True` and another forgetting it.
    """
    return search_begin(obs, manual_coin=True, **_hidden_info_kwargs(obs, my_deck))


def _rollout_our_turn(search_id, obs, my_index, deadline, live):
    """Replay the rest of our own turn with the base policy.

    Returns the final observation reached. Stops at the turn boundary -- what the opponent does
    next is not something this layer claims to know. Every intermediate search id is appended to
    `live` so the caller can release all of them.
    """
    cur_obs, sid = obs, search_id
    for _ in range(SEARCH_MAX_PLIES):
        if time.time() > deadline:
            return cur_obs
        if cur_obs.current.result != -1:
            return cur_obs
        if cur_obs.current.yourIndex != my_index:
            return cur_obs                        # opponent to act: our turn is over
        if cur_obs.select is None or not cur_obs.select.option:
            return cur_obs
        picks = choose_options(cur_obs)
        if not picks:
            return cur_obs
        state = search_step(sid, picks)
        cur_obs, sid = state.observation, state.searchId
        live.append(sid)
    return cur_obs


def _rollout_to_terminal(search_id, obs, my_index, deadline, live):
    """Continue a rollout past the turn boundary to a real terminal state.

    `_rollout_our_turn` stops when the opponent is to act, because no opponent-policy model
    exists. This uses the same base policy (`choose_options`) as a stand-in for BOTH sides instead
    -- it reads `obs.current.yourIndex` dynamically, so calling it on an opponent-turn observation
    plays the opponent's side by the same heuristic ranking used for our own. That is a real
    approximation, not a guess about the opponent's hidden cards (those are handled separately, by
    resampling `_hidden_info_kwargs` once per PIMC draw) -- it is the same bet the Orbit Wars
    winners made when they scored terminal win/loss instead of hand-weighting a board.

    Manual coin flips (`SelectContext.COIN_HEAD`) are intercepted and answered by `_pick_coin`
    rather than handed to `choose_options`, which has no branch for a decision that never reaches
    it outside of search. Returns `(final_obs, terminated)`; `terminated` is False on a budget or
    ply-count cutoff, meaning the caller has no real win/loss verdict for this draw.
    """
    cur_obs, sid = obs, search_id
    for _ in range(SEARCH_MAX_TOTAL_PLIES):
        if time.time() > deadline:
            return cur_obs, False
        if cur_obs.current.result != -1:
            return cur_obs, True
        if cur_obs.select is None or not cur_obs.select.option:
            return cur_obs, False
        if cur_obs.select.context == SelectContext.COIN_HEAD:
            picks = _pick_coin(cur_obs, my_index)
        else:
            picks = choose_options(cur_obs)
        if not picks:
            return cur_obs, False
        state = search_step(sid, picks)
        cur_obs, sid = state.observation, state.searchId
        live.append(sid)
    return cur_obs, False


def _pimc_score(obs, my_deck, my_index, first_option, deadline):
    """Average win/loss over `PIMC_DETERMINIZATIONS` resampled full-game rollouts.

    For each draw: resample the opponent's guessed hidden information fresh (a different
    plausible hand/deck/prize split from the matched archetype each time), start a new search
    from the same real, current observation, apply `first_option`, then roll both sides to a
    terminal state with the base policy. Scores `+1` win / `-1` loss / `0` draw-cutoff, averaged.
    Returns `None` if no draw reached a real terminal state before the deadline -- an unscoreable
    candidate should not silently look like a tie against one that is scoreable.

    This is the whole point of the PIMC replacement: no hand-picked weight exists here for a
    future matchup to expose as wrong. The only free parameters are how many times we resample
    (`PIMC_DETERMINIZATIONS`) and how far we're willing to roll out (`SEARCH_MAX_TOTAL_PLIES`),
    both budget knobs, not judgements about the game.
    """
    total, scored = 0, 0
    for _ in range(PIMC_DETERMINIZATIONS):
        if time.time() > deadline:
            break
        live = []
        try:
            root = _search_begin_determinized(obs, my_deck)
        except Exception:
            continue
        live.append(root.searchId)
        try:
            child = search_step(root.searchId, [first_option])
            live.append(child.searchId)
            final_obs, terminated = _rollout_to_terminal(
                child.searchId, child.observation, my_index, deadline, live)
            _search_stats["pimc_playouts"] += 1
            if terminated:
                scored += 1
                if final_obs.current.result == my_index:
                    total += 1
                elif final_obs.current.result != -1:
                    total -= 1
        except Exception:
            pass
        finally:
            for sid in live:
                try:
                    search_release(sid)
                except Exception:
                    pass
    return (total / scored) if scored > 0 else None


def search_reorder(obs, base_selected):
    """Return an option list for a MAIN decision, or `base_selected` unchanged.

    Two passes. First, a cheap single-determinization lethal/veto check -- always active for
    "lethal" and "veto" modes, and as a free win-detecting shortcut before "pimc" scoring, since a
    line that KOs a visible opponent active does not need six resampled rollouts to confirm it
    wins. Second, only in "pimc" mode and only if the first pass found neither a win nor (in veto
    mode) a survivor, a full PIMC pass scores every candidate by resampled terminal rollouts.
    Anything else -- an error, a budget overrun, a non-MAIN context, a multi-select, an exhausted
    game time bank, a tie -- returns the base policy's answer untouched.
    """
    if SEARCH_MODE == "off" or not _SEARCH_OK:
        return base_selected
    if obs.select is None or obs.select.context != SelectContext.MAIN:
        return base_selected
    # One first action per line. Multi-select contexts are not MAIN in this engine, but guard
    # rather than silently reordering something this layer did not reason about.
    if obs.select.maxCount != 1 or not base_selected:
        return base_selected

    global _game_search_seconds
    if _game_search_seconds >= SEARCH_GAME_TIME_CAP:
        # Time-bank exhausted: ~50 decisions each spending up to their own per-decision cap can
        # still blow the 600s game budget in aggregate. Fall through to the base policy, the same
        # fail-closed behavior as any other search error.
        _search_stats["game_capped"] += 1
        return base_selected

    _search_stats["calls"] += 1
    t_start = time.time()
    deadline = t_start + SEARCH_TIME_BUDGET
    my_index = obs.current.yourIndex
    my_deck = read_deck_csv()
    n_options = len(obs.select.option)
    seen = set(base_selected)
    order = list(base_selected) + [i for i in range(n_options) if i not in seen]
    candidates = order[:SEARCH_MAX_CANDIDATES]

    try:
        root = _search_begin_determinized(obs, my_deck)
        _search_stats["began"] += 1
    except Exception:
        _search_stats["errors"] += 1
        _game_search_seconds += time.time() - t_start
        return base_selected

    live = [root.searchId]
    try:
        for first in candidates:
            if time.time() > deadline:
                _search_stats["budget"] += 1
                break
            try:
                child = search_step(root.searchId, [first])
            except Exception:
                # An option the engine rejects in search is one we should not have offered it;
                # skip it rather than abandoning the whole decision.
                _search_stats["errors"] += 1
                continue
            live.append(child.searchId)
            final = _rollout_our_turn(
                child.searchId, child.observation, my_index, deadline, live)

            if final.current.result == my_index:
                # A proven win this turn ends the search: nothing scores higher, in any mode.
                _search_stats["lethal"] += 1
                if first != base_selected[0]:
                    _search_stats["changed"] += 1
                return [first]

            if SEARCH_MODE == "veto":
                # Veto-only: never reorder on judgement, only refuse a first action the rollout
                # proves ends the game against us this turn. Games here are decided by deck-out
                # and board wipe, not prizes (0 of 40 sampled games ended on prizes), and both are
                # states the engine reports exactly. Refusing a proven loss needs no weights, so
                # unlike a scored evaluator it cannot be mis-tuned -- it either fires or it does
                # not. The first surviving option in base-policy order wins, so the heuristic's
                # ranking is preserved everywhere it is not walking into a loss.
                if final.current.result != -1:
                    _search_stats["vetoed"] += 1
                    continue
                if first != base_selected[0]:
                    _search_stats["changed"] += 1
                return [first]
    except Exception:
        _search_stats["errors"] += 1
        _game_search_seconds += time.time() - t_start
        return base_selected
    finally:
        # Release every state created, on every path. The engine reuses the memory; leaking it
        # across ~51 decisions a battle is the difference between a working agent and an OOM.
        for sid in live:
            try:
                search_release(sid)
            except Exception:
                pass

    if SEARCH_MODE != "pimc":
        _game_search_seconds += time.time() - t_start
        return base_selected

    # No proven win or loss above: score every candidate by resampled terminal rollouts instead of
    # a hand-weighted board evaluator. The base policy's own answer is scored first (`candidates`
    # starts with `base_selected[0]`), so a tie -- or running out of budget before a second
    # candidate is even scoreable -- keeps its answer, the same discipline the old strict-
    # improvement-only board evaluator used.
    _search_stats["pimc_decisions"] += 1
    best_option, best_value = None, None
    for first in candidates:
        if time.time() > deadline:
            _search_stats["budget"] += 1
            break
        value = _pimc_score(obs, my_deck, my_index, first, deadline)
        if value is None:
            continue
        if best_value is None or value > best_value:
            best_option, best_value = first, value

    _game_search_seconds += time.time() - t_start
    if best_option is None:
        return base_selected
    if best_option != base_selected[0]:
        _search_stats["changed"] += 1
    return [best_option]
