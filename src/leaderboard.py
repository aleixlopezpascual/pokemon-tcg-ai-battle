"""Fetch the full public leaderboard and build a team-name -> score lookup.

Used to join episode replays' `info.TeamNames` against real current competitive scores, so
imitation-learning training data can be weighted toward stronger players rather than treated
uniformly. `kaggle competitions leaderboard <slug> -d` downloads the full CSV in one call
(confirmed: 6,497 teams, not the ~12-row page the `--show` table prints).

Usage:
    python src/leaderboard.py --out data/raw/leaderboard.csv
"""

import argparse
import csv
import subprocess
import unicodedata
import zipfile
from pathlib import Path

COMPETITION = "pokemon-tcg-ai-battle"


def normalize(name: str) -> str:
    if not name:
        return ""
    return unicodedata.normalize("NFKC", name).casefold().strip()


def fetch_leaderboard(out_csv: Path) -> Path:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    zip_path = out_csv.parent / "leaderboard_download.zip"
    subprocess.run(
        ["kaggle", "competitions", "leaderboard", COMPETITION, "-d", "-p", str(out_csv.parent)],
        check=True,
    )
    downloaded_zip = out_csv.parent / f"{COMPETITION}.zip"
    with zipfile.ZipFile(downloaded_zip) as z:
        member = z.namelist()[0]
        z.extract(member, out_csv.parent)
        (out_csv.parent / member).rename(out_csv)
    downloaded_zip.unlink(missing_ok=True)
    return out_csv


def build_lookup(csv_path: Path) -> dict:
    """normalized_name -> score, keyed by both TeamName and each split TeamMemberUserNames entry."""
    lookup = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                score = float(row["Score"])
            except (ValueError, KeyError):
                continue
            team_name = normalize(row.get("TeamName", ""))
            if team_name:
                lookup[team_name] = score
            members = row.get("TeamMemberUserNames", "") or ""
            for member in members.split(","):
                member_norm = normalize(member)
                if member_norm and member_norm not in lookup:
                    lookup[member_norm] = score
    return lookup


def score_for(lookup: dict, team_name: str):
    if not team_name:
        return None
    return lookup.get(normalize(team_name))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/raw/leaderboard.csv")
    args = parser.parse_args()
    out_path = fetch_leaderboard(Path(args.out))
    lookup = build_lookup(out_path)
    print(f"fetched {out_path}, {len(lookup)} name->score entries")
