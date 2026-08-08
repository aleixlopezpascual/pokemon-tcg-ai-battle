"""Turn raw (select, current, action) decision records into a fixed-width training table.

Model shape: score each legal option and pick the highest (matches every rule-based agent's
architecture in this repo) — so each row is one (decision, option) pair with a binary label
(was this option's position chosen). `action` is a list of 0-based *positions* into
`select.option` (confirmed against real replay data and the run-battle skill's docs), so no
card-identity matching is needed for the label itself — only for enriching option features.

AreaType/SelectType/OptionType integer values below are copied from the competition's own
`cg/api.py` enums (not guessed) so option/context fields decode to the right zone.
"""

import csv
import json
from pathlib import Path

AREA_DECK = 1
AREA_HAND = 2
AREA_DISCARD = 3
AREA_ACTIVE = 4
AREA_BENCH = 5
AREA_PRIZE = 6
AREA_STADIUM = 7
AREA_LOOKING = 12

# OptionType values, from cg/api.py's own enum (not guessed).
OPT_NUMBER = 0
OPT_CARD = 3
OPT_TOOL_CARD = 4
OPT_ENERGY_CARD = 5
OPT_ENERGY = 6
OPT_PLAY = 7
OPT_ATTACH = 8
OPT_EVOLVE = 9
OPT_ABILITY = 10
OPT_DISCARD = 11
OPT_RETREAT = 12
OPT_ATTACK = 13
OPT_END = 14

REPO_ROOT = Path(__file__).resolve().parent.parent
CARD_DATA_CSV = REPO_ROOT / "data" / "raw" / "EN Card Data.csv"
ATTACK_DATA_CSV = REPO_ROOT / "data" / "raw" / "EN_Attack_Data.csv"

NEUTRAL_SCORE = 1150.0  # "how would a ~1150-rated player play" — used at inference (no real
                          # opponent score is knowable mid-game) and for training records with
                          # no leaderboard join (the original 299-episode data, pre-Task-2).


def _score_norm(score) -> float:
    s = score if score is not None else NEUTRAL_SCORE
    return (s - 1000.0) / 200.0


def sample_weight(actor_score, actor_reward) -> float:
    """Weight training rows toward stronger, winning players. Records with no leaderboard join
    (actor_score is None) get the neutral weight of 1.0 pre-reward-multiplier."""
    base = 1.0 if actor_score is None else max(0.6, min(1.6, 1.0 + (actor_score - 1000.0) / 200.0))
    won = (actor_reward or 0) > 0
    return base * (1.5 if won else 1.0)


def load_attack_data(csv_path: Path = ATTACK_DATA_CSV) -> dict:
    """attackId -> {damage: int, energyCost: int, energies: list[int] (typed EnergyType ids)}"""
    attacks = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                attack_id = int(row["attackId"])
            except (ValueError, KeyError):
                continue
            energies_raw = row.get("energies", "") or ""
            energies = [int(e) for e in energies_raw.split("|") if e != ""]
            attacks[attack_id] = {
                "damage": int(row.get("damage", 0) or 0),
                "energyCost": len(energies),
                "energies": energies,
            }
    return attacks


CARD_ATTRS_CSV = REPO_ROOT / "data" / "raw" / "EN_Card_Attrs.csv"


def load_card_attrs(csv_path: Path = CARD_ATTRS_CSV) -> dict:
    """cardId -> {retreatCost, ex, megaEx, tera, energyType, weakness, resistance,
    evolvesFrom (bool: has one), n_attacks, basic, attacks (list[int] of attack IDs)}"""
    attrs = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                card_id = int(row["cardId"])
            except (ValueError, KeyError):
                continue
            attrs[card_id] = {
                "retreatCost": int(row.get("retreatCost", 0) or 0),
                "ex": int(row.get("ex", 0) or 0),
                "megaEx": int(row.get("megaEx", 0) or 0),
                "tera": int(row.get("tera", 0) or 0),
                "energyType": int(row.get("energyType", -1) or -1),
                "weakness": int(row["weakness"]) if row.get("weakness") not in (None, "", "None") else -1,
                "resistance": int(row["resistance"]) if row.get("resistance") not in (None, "", "None") else -1,
                "has_evolvesFrom": int(bool(row.get("evolvesFrom"))),
                "n_attacks": int(row.get("n_attacks", 0) or 0),
                "basic": int(row.get("basic", 0) or 0),
                "attacks": [int(a) for a in (row.get("attacks") or "").split("|") if a != ""],
            }
    return attrs


# Fixed mapping so train/inference always agree, regardless of CSV row order.
STAGE_CODES = {
    "Basic Pokémon": 1,
    "Stage 1 Pokémon": 2,
    "Stage 2 Pokémon": 3,
    "Basic Energy": 4,
    "Special Energy": 5,
    "Item": 6,
    "Supporter": 7,
    "Stadium": 8,
    "Pokémon Tool": 9,
}


def load_card_data(csv_path: Path = CARD_DATA_CSV) -> dict:
    """card_id -> {hp: float|None, is_pokemon: bool, stage_code: int}"""
    cards = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                card_id = int(row["Card ID"])
            except (ValueError, KeyError):
                continue
            hp_raw = row.get("HP", "n/a")
            try:
                hp = float(hp_raw)
            except ValueError:
                hp = None
            stage_raw = row.get("Stage (Pokémon)/Type (Energy and Trainer)", "")
            cards[card_id] = {
                "hp": hp,
                "is_pokemon": hp is not None,
                "stage_code": STAGE_CODES.get(stage_raw, 0),
            }
    return cards


def _zone_cards(current: dict, player_index: int, area: int):
    if player_index is None or area is None:
        return None
    players = current.get("players", [])
    if player_index >= len(players):
        return None
    player = players[player_index]
    if area == AREA_HAND:
        return player.get("hand")
    if area == AREA_DISCARD:
        return player.get("discard")
    if area == AREA_ACTIVE:
        return player.get("active")
    if area == AREA_BENCH:
        return player.get("bench")
    if area == AREA_PRIZE:
        return player.get("prize")
    return None  # DECK/ENERGY/TOOL/PRE_EVOLUTION — not resolved in this version


def _at(zone, index):
    if not zone or index is None or index >= len(zone):
        return None
    return zone[index]


def resolve_option(option: dict, select: dict, current: dict):
    """Resolve an option to (source_card_id, target_pokemon_dict).

    Per cg/api.py's OptionType docstrings, several types omit `area`/`playerIndex` because
    they're implicit: PLAY only has `index` (your own hand); ATTACH/EVOLVE's `area`/`index` is
    the card being attached/evolved (your own side) and `inPlayArea`/`inPlayIndex` is the target
    Pokemon (also your own side — you can't attach to the opponent's). ABILITY/DISCARD have
    `area`/`index` but no `playerIndex` (also implicitly your own side, except STADIUM which is
    shared). CARD is the one type with `area`/`index`/`playerIndex` all explicit, except when
    `area` is DECK or LOOKING — those live in `select.deck`/`current.looking`, not a per-player
    zone, and aren't keyed by playerIndex at all.
    """
    opt_type = option.get("type")
    your_index = current.get("yourIndex")
    source_card_id = None
    target = None

    if opt_type == OPT_PLAY:
        hand = _zone_cards(current, your_index, AREA_HAND)
        card = _at(hand, option.get("index"))
        source_card_id = card.get("id") if card else None

    elif opt_type in (OPT_ATTACH, OPT_EVOLVE):
        area = option.get("area", AREA_HAND)
        zone = _zone_cards(current, your_index, area)
        card = _at(zone, option.get("index"))
        source_card_id = card.get("id") if card else None
        target_zone = _zone_cards(current, your_index, option.get("inPlayArea"))
        target = _at(target_zone, option.get("inPlayIndex"))

    elif opt_type in (OPT_ABILITY, OPT_DISCARD):
        area = option.get("area")
        if area == AREA_STADIUM:
            card = _at(current.get("stadium"), option.get("index"))
        else:
            zone = _zone_cards(current, your_index, area)
            card = _at(zone, option.get("index"))
        source_card_id = card.get("id") if card else None
        if opt_type == OPT_ABILITY and area in (AREA_ACTIVE, AREA_BENCH):
            target = card  # the ability-user itself is the relevant Pokemon context

    elif opt_type == OPT_CARD:
        area = option.get("area")
        if area == AREA_DECK:
            card = _at(select.get("deck"), option.get("index"))
        elif area == AREA_LOOKING:
            card = _at(current.get("looking"), option.get("index"))
        elif area == AREA_PRIZE:
            card = None  # genuinely face-down, unresolvable
        else:
            zone = _zone_cards(current, option.get("playerIndex"), area)
            card = _at(zone, option.get("index"))
        source_card_id = card.get("id") if card else None

    elif opt_type in (OPT_TOOL_CARD, OPT_ENERGY_CARD, OPT_ENERGY):
        zone = _zone_cards(current, option.get("playerIndex"), option.get("area"))
        pokemon = _at(zone, option.get("index"))
        target = pokemon
        if pokemon:
            if opt_type == OPT_TOOL_CARD:
                card = _at(pokemon.get("tools"), option.get("toolIndex"))
            else:
                card = _at(pokemon.get("energyCards"), option.get("energyIndex"))
            source_card_id = card.get("id") if card else None

    # RETREAT/END/ATTACK/NUMBER/YES/NO: nothing to resolve (ATTACK's attackId is handled
    # separately in option_features; the rest have no card/Pokemon reference at all).

    return source_card_id, target


def global_features(select: dict, current: dict, actor_score=None, opp_score=None) -> dict:
    your_index = current.get("yourIndex")
    players = current.get("players", [])
    you = players[your_index] if your_index is not None and your_index < len(players) else {}
    opp_index = 1 - your_index if your_index in (0, 1) else None
    opp = players[opp_index] if opp_index is not None and opp_index < len(players) else {}

    def pokemon_hp(p):
        active = p.get("active") or []
        if not active or active[0] is None:
            return 0.0
        return float(active[0].get("hp", 0) or 0)

    return {
        "turn": current.get("turn", 0) or 0,
        "turnActionCount": current.get("turnActionCount", 0) or 0,
        "energyAttached": int(bool(current.get("energyAttached"))),
        "supporterPlayed": int(bool(current.get("supporterPlayed"))),
        "stadiumPlayed": int(bool(current.get("stadiumPlayed"))),
        "retreated": int(bool(current.get("retreated"))),
        "you_active_hp": pokemon_hp(you),
        "you_bench_count": len(you.get("bench") or []),
        "you_hand_count": you.get("handCount", 0) or 0,
        "you_discard_count": len(you.get("discard") or []),
        "you_deck_count": you.get("deckCount", 0) or 0,
        "you_prize_count": len(you.get("prize") or []),
        "opp_active_hp": pokemon_hp(opp),
        "opp_bench_count": len(opp.get("bench") or []),
        "opp_hand_count": opp.get("handCount", 0) or 0,
        "opp_discard_count": len(opp.get("discard") or []),
        "opp_deck_count": opp.get("deckCount", 0) or 0,
        "opp_prize_count": len(opp.get("prize") or []),
        "select_type": select.get("type", -1),
        "select_context": select.get("context", -1),
        "select_minCount": select.get("minCount", 1) or 1,
        "select_maxCount": select.get("maxCount", 1) or 1,
        "actor_score_norm": _score_norm(actor_score),
        "opp_score_norm": _score_norm(opp_score),
    }


def _cheapest_attack_gap(pokemon_card_ids: list, energy_count: int, attack_data: dict, card_attrs: dict) -> int:
    """Given a Pokemon's card id and current energy count, return how many MORE energy
    attachments its cheapest known attack still needs (0 if already affordable)."""
    attrs = (card_attrs or {}).get(pokemon_card_ids, {})
    attack_ids = attrs.get("attacks") or []
    costs = [attack_data.get(aid, {}).get("energyCost") for aid in attack_ids]
    costs = [c for c in costs if c is not None]
    if not costs:
        return -1  # no known attacks (e.g. not evolved enough yet, or data gap) — unresolvable
    cheapest = min(costs)
    return max(0, cheapest - energy_count)


def option_features(
    option: dict,
    select: dict,
    current: dict,
    card_data: dict,
    attack_data: dict = None,
    card_attrs: dict = None,
    g: dict = None,
) -> dict:
    card_id, target = resolve_option(option, select, current)
    card = card_data.get(card_id, {}) if card_id is not None else {}
    attrs = (card_attrs or {}).get(card_id, {}) if card_id is not None else {}
    attack_id = option.get("attackId")
    attack = (attack_data or {}).get(attack_id, {}) if attack_id is not None else {}
    target_card = card_data.get(target.get("id"), {}) if target else {}

    opp_active_hp = (g or {}).get("opp_active_hp", 0) or 0
    is_lethal = int(option.get("type") == OPT_ATTACK and attack.get("damage", 0) >= opp_active_hp > 0)

    energy_gap_before = -1
    energy_gap_after = -1
    if option.get("type") == OPT_ATTACH and target:
        target_energy_count = len(target.get("energyCards") or [])
        energy_gap_before = _cheapest_attack_gap(target.get("id"), target_energy_count, attack_data, card_attrs)
        if energy_gap_before != -1:
            energy_gap_after = max(0, energy_gap_before - 1)

    return {
        "opt_type": option.get("type", -1),
        "opt_area": option.get("area", -1) if option.get("area") is not None else -1,
        "opt_index": option.get("index", -1) if option.get("index") is not None else -1,
        "opt_playerIndex": option.get("playerIndex", -1) if option.get("playerIndex") is not None else -1,
        "opt_number": option.get("number", -1) if option.get("number") is not None else -1,
        "opt_attackId": attack_id if attack_id is not None else -1,
        "opt_attack_damage": attack.get("damage", -1),
        "opt_attack_energyCost": attack.get("energyCost", -1),
        "opt_is_lethal": is_lethal,
        "opt_inPlayArea": option.get("inPlayArea", -1) if option.get("inPlayArea") is not None else -1,
        "opt_card_id": card_id if card_id is not None else -1,
        "opt_card_hp": card.get("hp") or -1,
        "opt_card_stage": card.get("stage_code", 0),
        "opt_card_retreatCost": attrs.get("retreatCost", -1),
        "opt_card_ex": attrs.get("ex", 0),
        "opt_card_megaEx": attrs.get("megaEx", 0),
        "opt_card_energyType": attrs.get("energyType", -1),
        "opt_card_has_evolvesFrom": attrs.get("has_evolvesFrom", 0),
        "opt_card_is_basic": attrs.get("basic", 0),
        "opt_card_n_attacks": attrs.get("n_attacks", -1),
        "opt_is_own": int(option.get("playerIndex", current.get("yourIndex")) == current.get("yourIndex")),
        "opt_target_card_id": target.get("id", -1) if target else -1,
        "opt_target_hp": (target.get("hp") if target else None) or -1,
        "opt_target_maxHp": target_card.get("hp") or -1,
        "opt_target_n_energies": len(target.get("energyCards") or []) if target else -1,
        "opt_target_n_tools": len(target.get("tools") or []) if target else -1,
        "opt_target_appearThisTurn": int(bool(target.get("appearThisTurn"))) if target else -1,
        "opt_energy_gap_before": energy_gap_before,
        "opt_energy_gap_after": energy_gap_after,
    }


FEATURE_COLUMNS = None  # set on first call to records_to_rows, kept stable after that


def _add_listwise_features(rows: list) -> None:
    """Mutate rows in-place: context computed across all options of the same decision."""
    n = len(rows)
    damages = [r.get("opt_attack_damage", -1) for r in rows]
    max_damage = max(damages) if damages else -1
    any_lethal = any(r.get("opt_is_lethal") for r in rows)
    type_counts = {}
    for r in rows:
        type_counts[r["opt_type"]] = type_counts.get(r["opt_type"], 0) + 1
    for r, dmg in zip(rows, damages):
        r["opt_n_options_in_decision"] = n
        r["opt_is_only_of_type"] = int(type_counts[r["opt_type"]] == 1)
        r["opt_is_max_damage"] = int(dmg == max_damage and dmg > 0)
        r["opt_is_lethal_available_in_decision"] = int(any_lethal)


_EQUIVALENCE_ELIGIBLE_TYPES = {
    OPT_PLAY, OPT_ATTACH, OPT_EVOLVE, OPT_ABILITY, OPT_DISCARD,
    OPT_TOOL_CARD, OPT_ENERGY_CARD, OPT_ENERGY, OPT_ATTACK,
}


def _option_signature(row: dict, index: int) -> tuple:
    """Two options are functionally equivalent only when their type has a genuinely
    discriminating resolved field (card identity and/or attack identity) — see
    resolve_option()'s own docstring for which types those are. Options of any other type
    (OPT_NUMBER, OPT_RETREAT, OPT_END, and OPT_CARD referencing a face-down AREA_PRIZE card,
    which resolve_option itself calls "genuinely face-down, unresolvable") fall back to a
    per-index signature, so they are never wrongly grouped as equivalent to a different real
    choice that merely also failed to resolve a card id."""
    opt_type = row["opt_type"]
    eligible = opt_type in _EQUIVALENCE_ELIGIBLE_TYPES or (
        opt_type == OPT_CARD and row.get("opt_area") != AREA_PRIZE
    )
    if not eligible:
        return ("idx", index)
    return (opt_type, row["opt_card_id"], row.get("opt_target_card_id", -1), row.get("opt_attackId", -1))


def records_to_rows(records, card_data: dict, attack_data: dict = None, card_attrs: dict = None):
    """Yield (feature_dict, label, decision_key, weight) for every (decision, option) pair.
    All options sharing the chosen option's equivalence signature are labeled positive, not just
    the literal chosen index — see _option_signature."""
    for rec_idx, rec in enumerate(records):
        select = rec["select"]
        current = rec["current"]
        action = rec["action"]
        g = global_features(select, current, rec.get("actor_score"), rec.get("opp_score"))
        w = sample_weight(rec.get("actor_score"), rec.get("actor_reward"))
        options = select.get("option") or []
        rows = [option_features(option, select, current, card_data, attack_data, card_attrs, g) for option in options]
        _add_listwise_features(rows)
        chosen_signatures = {_option_signature(rows[i], i) for i in action if i < len(rows)}
        for i, o in enumerate(rows):
            row = {**g, **o}
            label = 1 if _option_signature(o, i) in chosen_signatures else 0
            yield row, label, rec_idx, w


def build_dataset(records_path: str, card_data_path: str = None, attack_data_path: str = None,
                   card_attrs_path: str = None, max_records: int = None):
    """Load JSONL records and return (rows, labels, decision_ids, weights) as parallel lists."""
    card_data = load_card_data(Path(card_data_path) if card_data_path else CARD_DATA_CSV)
    attack_data = load_attack_data(Path(attack_data_path) if attack_data_path else ATTACK_DATA_CSV)
    card_attrs = load_card_attrs(Path(card_attrs_path) if card_attrs_path else CARD_ATTRS_CSV)
    records = []
    with open(records_path) as f:
        for i, line in enumerate(f):
            if max_records is not None and i >= max_records:
                break
            records.append(json.loads(line))

    rows, labels, decision_ids, weights = [], [], [], []
    for row, label, decision_id, w in records_to_rows(records, card_data, attack_data, card_attrs):
        rows.append(row)
        labels.append(label)
        decision_ids.append(decision_id)
        weights.append(w)
    return rows, labels, decision_ids, weights


if __name__ == "__main__":
    rows, labels, decision_ids, weights = build_dataset("data/processed/il_records.jsonl")
    print(f"{len(rows)} (decision, option) rows from {len(set(decision_ids))} decisions")
    print(f"positive rate: {sum(labels) / len(labels):.3f}")
    print(f"mean sample weight: {sum(weights) / len(weights):.3f}")
    print("sample row:", rows[0])
