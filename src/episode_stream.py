"""Stream-download a day's full episode dataset and extract IL decision records directly,
without ever writing the ~4,500 individual episode JSONs to disk.

Downloads one whole-day zip (~750MB compressed, not the ~21GB uncompressed figure the daily
manifest implies), reads each member directly from the zip into memory, joins its participants
against the leaderboard score lookup, and only keeps episodes where at least one side clears the
score floor. The zip itself is deleted after processing — peak extra disk is one zip, not
~18GB of loose JSON.

Usage:
    python src/episode_stream.py --day 2026-08-05 --out data/processed/il_records_2026-08-05.jsonl
"""

import argparse
import json
import subprocess
import zipfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leaderboard import build_lookup, score_for, normalize  # noqa: E402
from episode_pipeline import extract_records_from_dict  # noqa: E402

SCORE_FLOOR = 950.0


def stream_day(day: str, lookup: dict, out_path: Path, score_floor: float = SCORE_FLOOR):
    ref = f"kaggle/pokemon-tcg-ai-battle-episodes-{day}"
    zip_dir = Path("data/raw/episode_zips")
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{day}.zip"

    print(f"downloading {ref}...")
    subprocess.run(
        ["kaggle", "datasets", "download", ref, "-p", str(zip_dir)],
        check=True,
    )
    downloaded = zip_dir / f"pokemon-tcg-ai-battle-episodes-{day}.zip"
    if not downloaded.exists():
        # fallback: whatever single zip landed in the dir
        candidates = list(zip_dir.glob("*.zip"))
        downloaded = candidates[0]

    kept, seen, tripwire = 0, 0, 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(downloaded) as z, out_path.open("w") as out_f:
        names = [n for n in z.namelist() if n.endswith(".json")]
        for name in names:
            seen += 1
            try:
                data = json.loads(z.read(name))
            except json.JSONDecodeError:
                continue
            team_names = (data.get("info") or {}).get("TeamNames") or [None, None]
            scores = [score_for(lookup, t) for t in team_names]
            keep_sides = {i for i, s in enumerate(scores) if s is not None and s >= score_floor}
            if not keep_sides:
                continue
            kept += 1
            records, tw = extract_records_from_dict(data, scores=scores)
            tripwire += tw
            for r in records:
                if r["player"] in keep_sides:
                    out_f.write(json.dumps(r) + "\n")

    downloaded.unlink(missing_ok=True)
    print(f"{day}: {kept}/{seen} episodes kept (>=1 side score >= {score_floor}), "
          f"{tripwire} tripwire failures -> {out_path}")
    return kept, seen


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", default=None)
    parser.add_argument("--score-floor", type=float, default=SCORE_FLOOR)
    parser.add_argument("--leaderboard", default="data/raw/leaderboard.csv")
    args = parser.parse_args()

    lookup = build_lookup(Path(args.leaderboard))
    out = Path(args.out) if args.out else Path(f"data/processed/il_records_{args.day}.jsonl")
    stream_day(args.day, lookup, out, args.score_floor)
