---
name: secrets-and-data-guard
description: Pre-push safety checklist for this repo, which is currently private but will go public eventually. Scans git history and the staged diff for competition data (data/raw, data/processed) and credential-shaped strings (API keys, tokens, .kaggle/kaggle.json, .env files).
disable-model-invocation: true
---

# Secrets and Data Guard

This repo (`pokemon-tcg-ai-battle`) is private now but is expected to go public later. Run
this before pushing, and definitely before flipping visibility to public
(`gh repo edit --visibility public`).

## What it checks

Run the bundled script from the repo root:

```bash
bash .claude/skills/secrets-and-data-guard/scripts/scan.sh
```

It checks, in order:

1. **Git history** (`git log --all --name-only`) for any `data/raw/` or `data/processed/`
   file ever committed. A `.gitignore` added after the fact does not retroactively scrub
   files already in history — this is the check that catches that.
2. **Currently tracked files** for the same data paths, and for `.kaggle/` or `.env*` files.
3. **The staged diff** (`git diff --cached`) for credential-shaped strings: `api_key=`,
   `secret=`, `token=`, `password=` followed by a long alphanumeric value, a literal
   `kaggle.json` reference, or an AWS-style access key pattern.

Exit code is non-zero if anything fails.

## If it fails

- **Data in history**: this needs history rewriting (`git filter-repo` or BFG), not just a
  new commit — deleting the file in a new commit still leaves it in old commits' history.
  Stop and confirm with the user before rewriting history, especially if it's already
  pushed, since it changes commit hashes for anyone else with a clone.
- **Credential-shaped string staged**: unstage it (`git restore --staged <file>`), remove
  the secret from the file, and if it was a real credential (not a placeholder/example),
  tell the user to rotate it — a value that touched a git diff should be treated as
  potentially exposed even if never pushed.
- **Data files tracked**: `git rm --cached` them (keeps the local file, just untracks it),
  confirm they're covered by `.gitignore`, then re-run the scan.

## Note on scope

This is a heuristic pattern scan, not a guarantee — it catches the common shapes of
mistakes (Kaggle credentials, obvious API key formats, the competition's own data
directories) but won't catch a secret pasted in an unusual format. When in doubt about
whether something is sensitive, ask the user rather than assuming it's fine.
