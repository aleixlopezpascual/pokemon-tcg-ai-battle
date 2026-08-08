"""Regenerate data/raw/EN_Card_Attrs.csv with an added `attacks` column (pipe-joined attack IDs
per card) — the file already has every other column this script reproduces, but was originally
generated ad-hoc with no checked-in script. cg.api.CardData.attacks (list[int]) is exactly what's
needed for the energy_gap feature (does this ATTACH turn on an attack) and didn't exist as a
column before (only n_attacks, a count).

Usage (run from repo root, with an engine-bearing submission directory locatable):
    python src/export_card_attacks.py --engine-dir submissions/masamikobayashi_archaludon_cinderace --out data/raw/EN_Card_Attrs.csv
"""

import argparse
import csv
import sys
from pathlib import Path


def export(engine_dir: str, out_path: str):
    sys.path.insert(0, engine_dir)
    from cg.api import all_card_data

    cards = all_card_data()
    fieldnames = [
        "cardId", "cardType", "retreatCost", "hp", "weakness", "resistance", "energyType",
        "basic", "stage1", "stage2", "ex", "megaEx", "tera", "aceSpec", "evolvesFrom",
        "n_attacks", "attacks",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in cards:
            writer.writerow({
                "cardId": c.cardId,
                "cardType": int(c.cardType),
                "retreatCost": c.retreatCost,
                "hp": c.hp,
                "weakness": int(c.weakness) if c.weakness is not None else "",
                "resistance": int(c.resistance) if c.resistance is not None else "",
                "energyType": int(c.energyType) if c.energyType is not None else -1,
                "basic": int(c.basic),
                "stage1": int(c.stage1),
                "stage2": int(c.stage2),
                "ex": int(c.ex),
                "megaEx": int(c.megaEx),
                "tera": int(c.tera),
                "aceSpec": int(c.aceSpec),
                "evolvesFrom": c.evolvesFrom or "",
                "n_attacks": len(c.attacks or []),
                "attacks": "|".join(str(a) for a in (c.attacks or [])),
            })
    print(f"exported {len(cards)} cards -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine-dir", required=True, help="A submission dir containing a cg/ package")
    parser.add_argument("--out", default="data/raw/EN_Card_Attrs.csv")
    args = parser.parse_args()
    export(args.engine_dir, args.out)
