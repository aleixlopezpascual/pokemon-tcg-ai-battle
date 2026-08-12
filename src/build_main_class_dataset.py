"""Build a rating- and (optionally) deck-behavior-filtered MAIN-decision dataset for a trained
class-prior model — Task 8 (next) does the actual training/gating; this only builds the table.

MAIN decisions are the ones where an agent picks its whole action for a turn-step: `select.context
== 0` (`SelectContext.MAIN`, per `cg/api.py`), `select.maxCount == 1` (a single choice, not a
multi-select), with at least `min_options` legal options and a resolvable `action[0]` position.
The label is `option[action[0]]["type"]` — the OptionType of the chosen option (see
`features.py`'s OPT_* constants, copied from `cg/api.py`'s own enum).

Availability features are mandatory (not optional polish): `features.global_features` has no
per-option-type counts at all, and that omission is exactly what let the Track-2 intent classifier
degenerate into a legality detector (85.7% accuracy against an 87.7% majority baseline — it was
just learning "is this type legal here", not "would an expert pick it"). `decision_features` adds
11 columns on top of `global_features`'s 24 so the model has to reason about *which* legal option
is best, not just which types are legal.

Rating filter is the "Orbit Wars form": `actor_score >= score_floor OR (won AND opp_score >=
score_floor)` — a side counts as strong-enough if it hit the floor itself, or if it beat an
opponent who was already at the floor (a win against a strong player is evidence of strength even
if this side's own rating hasn't caught up yet).

Behavior filter (opt-in via `deck_jaccard_min`/`deck_ref`) restricts to sides playing a
deck close to a reference decklist (multiset Jaccard, via `deck_meta.jaccard` — copy counts
matter, so this is not a set comparison).

Both the rating and (deck) behavior facts are per-*side* (episode_id, player), not per-record —
every decision record within a side repeats the same `actor_score`/`opp_score`/`actor_reward`/
`actor_deck`, so they are computed once per distinct side the first time it's seen and cached,
rather than recomputed (esp. the Counter-based Jaccard) on every one of the 626,019 records.

Streams the 3.0 GB corpus line by line — never loaded whole into memory.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_meta  # noqa: E402
import features as feat  # noqa: E402

# Loaded once at import time (small CSV) so `decision_features` can look up ATTACK options'
# damage without needing attack_data threaded through its signature — matches the brief's
# `decision_features(select, current, actor_score=None, opp_score=None) -> dict` interface.
ATTACK_DATA = feat.load_attack_data()

MAIN_CONTEXT = 0


def decision_features(select: dict, current: dict, actor_score=None, opp_score=None) -> dict:
    """24 `global_features` columns + 11 availability/lethality columns = 35 total.

    The 11 additions: n_options, n_play, n_attach, n_evolve, n_ability, n_retreat, n_attack,
    n_end (per-type option counts — the missing signal that let a prior classifier become a
    legality detector), max_attack_damage, any_lethal, best_attack_kills_active.

    `any_lethal` and `best_attack_kills_active` are computed independently (any-attack-lethal
    vs. lethal-via-the-max-damage-attack) but are mathematically identical by construction: if
    any attack option is lethal, the max-damage attack option is at least as strong, so it is
    also lethal. Both columns are included anyway because the brief's fixed 35-column schema
    names them separately; keeping both keeps the schema stable even if a future revision makes
    them diverge (e.g. an attack with a lower base damage but a lethal on-hit effect).
    """
    g = feat.global_features(select, current, actor_score, opp_score)
    options = select.get("option") or []
    type_counts = Counter(o.get("type") for o in options)

    opp_active_hp = g.get("opp_active_hp", 0.0) or 0.0
    attack_damages = []
    for o in options:
        if o.get("type") != feat.OPT_ATTACK:
            continue
        dmg = ATTACK_DATA.get(o.get("attackId"), {}).get("damage")
        if dmg is not None:
            attack_damages.append(dmg)
    max_attack_damage = max(attack_damages) if attack_damages else 0
    is_lethal = int(bool(attack_damages) and opp_active_hp > 0 and max_attack_damage >= opp_active_hp)

    extra = {
        "n_options": len(options),
        "n_play": type_counts.get(feat.OPT_PLAY, 0),
        "n_attach": type_counts.get(feat.OPT_ATTACH, 0),
        "n_evolve": type_counts.get(feat.OPT_EVOLVE, 0),
        "n_ability": type_counts.get(feat.OPT_ABILITY, 0),
        "n_retreat": type_counts.get(feat.OPT_RETREAT, 0),
        "n_attack": type_counts.get(feat.OPT_ATTACK, 0),
        "n_end": type_counts.get(feat.OPT_END, 0),
        "max_attack_damage": max_attack_damage,
        "any_lethal": is_lethal,
        "best_attack_kills_active": is_lethal,
    }
    return {**g, **extra}


def _passes_rating(actor_score, opp_score, actor_reward, score_floor, require_win_or_strong_opp) -> bool:
    """The Orbit Wars form: `score >= floor OR (won AND opp_score >= floor)`."""
    if actor_score is not None and actor_score >= score_floor:
        return True
    if require_win_or_strong_opp:
        won = (actor_reward or 0) > 0
        if won and opp_score is not None and opp_score >= score_floor:
            return True
    return False


def _is_eligible_record(select: dict, action: list, min_options: int) -> bool:
    if select.get("context") != MAIN_CONTEXT:
        return False
    if select.get("maxCount") != 1:
        return False
    options = select.get("option") or []
    if len(options) < min_options:
        return False
    if not action or action[0] >= len(options):
        return False
    return True


def iter_main_decisions(records_path, score_floor: float = 1100.0, require_win_or_strong_opp: bool = True,
                         min_options: int = 2, deck_jaccard_min: float = None, deck_ref=None) -> Iterator[dict]:
    """Stream `records_path` and yield one dict per eligible, filtered MAIN decision:
    `{"features", "label", "avail", "episode_id", "weight", "side_jaccard"}`.

    `deck_ref` is a deck (list of card ids, or a Counter) to compare each side against via
    `deck_meta.jaccard`; `deck_jaccard_min` requires that similarity as a filter. Passing
    `deck_jaccard_min` without `deck_ref` is a caller error (nothing to compare against).
    """
    if deck_jaccard_min is not None and deck_ref is None:
        raise ValueError("deck_jaccard_min requires deck_ref")
    deck_ref_counter = Counter(deck_ref) if deck_ref else None

    side_cache: dict = {}  # (episode_id, player) -> {"passes_rating", "passes_deck", "weight", "side_jaccard"}

    with open(records_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # a truncated final line from an interrupted harvest

            select = rec.get("select") or {}
            action = rec.get("action") or []
            if not _is_eligible_record(select, action, min_options):
                continue

            side_key = (rec.get("episode_id"), rec.get("player"))
            side = side_cache.get(side_key)
            if side is None:
                actor_score = rec.get("actor_score")
                opp_score = rec.get("opp_score")
                actor_reward = rec.get("actor_reward")
                passes_rating = _passes_rating(actor_score, opp_score, actor_reward,
                                                score_floor, require_win_or_strong_opp)
                side_jaccard = None
                passes_deck = True
                if deck_ref_counter is not None:
                    side_jaccard = deck_meta.jaccard(rec.get("actor_deck") or [], deck_ref_counter)
                    passes_deck = deck_jaccard_min is None or side_jaccard >= deck_jaccard_min
                side = {
                    "passes_rating": passes_rating,
                    "passes_deck": passes_deck,
                    "side_jaccard": side_jaccard,
                    "weight": feat.sample_weight(actor_score, actor_reward),
                }
                side_cache[side_key] = side

            if not side["passes_rating"] or not side["passes_deck"]:
                continue

            options = select.get("option") or []
            label = options[action[0]].get("type")
            avail = sorted({o.get("type") for o in options})
            features = decision_features(select, rec.get("current") or {},
                                          rec.get("actor_score"), rec.get("opp_score"))

            yield {
                "features": features,
                "label": label,
                "avail": avail,
                "episode_id": rec.get("episode_id"),
                "weight": side["weight"],
                "side_jaccard": side["side_jaccard"],
            }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--records", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--score-floor", type=float, default=1100.0)
    p.add_argument("--win-or-strong-opp", dest="win_or_strong_opp", action="store_true", default=True,
                   help="Also accept a side below the floor if it beat an opponent at/above it (default: on).")
    p.add_argument("--no-win-or-strong-opp", dest="win_or_strong_opp", action="store_false")
    p.add_argument("--min-options", type=int, default=2)
    p.add_argument("--deck-ref", help="deck.csv (one card id per line) to Jaccard-filter sides against.")
    p.add_argument("--deck-jaccard-min", type=float, default=None)
    p.add_argument("--progress-every", type=int, default=200_000)
    args = p.parse_args()

    deck_ref = deck_meta.load_deck_csv(Path(args.deck_ref)) if args.deck_ref else None

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()
    n_written = 0
    episodes_seen = set()
    with out_path.open("w") as out_f:
        for i, row in enumerate(iter_main_decisions(
                args.records, score_floor=args.score_floor,
                require_win_or_strong_opp=args.win_or_strong_opp,
                min_options=args.min_options,
                deck_jaccard_min=args.deck_jaccard_min, deck_ref=deck_ref)):
            out_f.write(json.dumps(row) + "\n")
            n_written += 1
            episodes_seen.add(row["episode_id"])
            if args.progress_every and n_written % args.progress_every == 0:
                elapsed = time.time() - start
                print(f"  ...{n_written} rows written ({len(episodes_seen)} episodes, {elapsed:.0f}s elapsed)",
                      file=sys.stderr)

    elapsed = time.time() - start
    print(f"wrote {n_written} rows ({len(episodes_seen)} episodes) to {out_path} in {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
