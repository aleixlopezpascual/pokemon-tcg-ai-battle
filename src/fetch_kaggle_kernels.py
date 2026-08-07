"""Pull top public kernels for the PTCG AI Battle competition for local audit.

Usage:
    python src/fetch_kaggle_kernels.py --list-only
    python src/fetch_kaggle_kernels.py --pull kiyotah/reinforcement-learning-and-mcts-sample-code romanrozen/strong-start-baseline-agent-v10-lb-950
    python src/fetch_kaggle_kernels.py --pull-top 10

Requires the `kaggle` CLI to be installed and authenticated (~/.kaggle/kaggle.json).
Pulled kernel source lands under notebooks/kaggle-research/pulled/<ref-slug>/ (gitignored —
it's third-party code; only your own audit notes in notebooks/kaggle-research/ get committed).
"""

import argparse
import subprocess
import sys
from pathlib import Path

COMPETITION = "pokemon-tcg-ai-battle"
REPO_ROOT = Path(__file__).resolve().parent.parent
PULL_DIR = REPO_ROOT / "notebooks" / "kaggle-research" / "pulled"


def list_kernels(page_size: int = 50) -> list[dict]:
    result = subprocess.run(
        [
            "kaggle", "kernels", "list",
            "--competition", COMPETITION,
            "--sort-by", "voteCount",
            "--page-size", str(page_size),
            "--format", "json",
        ],
        capture_output=True, text=True, check=True,
    )
    import json
    return json.loads(result.stdout)


def print_kernels(kernels: list[dict]) -> None:
    for k in kernels:
        print(f"{k.get('totalVotes', '?'):>5}  {k['ref']:<70} {k.get('title', '')}")


def pull_kernel(ref: str) -> None:
    slug = ref.replace("/", "__")
    dest = PULL_DIR / slug
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["kaggle", "kernels", "pull", ref, "-p", str(dest)], check=True)
    print(f"pulled {ref} -> {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list-only", action="store_true", help="list top kernels and exit, no download")
    parser.add_argument("--pull", nargs="*", metavar="REF", help="pull specific kernel refs (owner/kernel-slug)")
    parser.add_argument("--pull-top", type=int, metavar="N", help="pull the top N kernels by vote count")
    args = parser.parse_args()

    kernels = list_kernels()

    if args.list_only or not (args.pull or args.pull_top):
        print_kernels(kernels)
        return

    refs = list(args.pull or [])
    if args.pull_top:
        refs += [k["ref"] for k in kernels[: args.pull_top] if k["ref"] not in refs]

    if not refs:
        print("no refs to pull", file=sys.stderr)
        sys.exit(1)

    for ref in refs:
        pull_kernel(ref)


if __name__ == "__main__":
    main()
