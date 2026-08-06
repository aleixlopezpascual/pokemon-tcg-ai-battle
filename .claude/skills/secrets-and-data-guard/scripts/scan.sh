#!/usr/bin/env bash
# Pre-push safety scan for pokemon-tcg-ai-battle (a repo that will eventually go public).
# Checks: (1) staged/tracked history never contains data/raw or data/processed contents,
#         (2) no credential-shaped strings are staged, (3) no .kaggle/.env files are tracked.
set -u
fail=0

echo "== Checking git history for competition data =="
if git log --all --name-only --pretty=format: | grep -E '^data/(raw|processed)/' | grep -v '\.gitkeep$' | sort -u | grep -q .; then
  echo "FAIL: competition data files found in git history:"
  git log --all --name-only --pretty=format: | grep -E '^data/(raw|processed)/' | grep -v '\.gitkeep$' | sort -u
  fail=1
else
  echo "OK: no data/raw or data/processed files in git history."
fi

echo
echo "== Checking currently tracked files for data/credential paths =="
if git ls-files | grep -E '^data/(raw|processed)/' | grep -v '\.gitkeep$' | grep -q .; then
  echo "FAIL: competition data files are currently tracked:"
  git ls-files | grep -E '^data/(raw|processed)/' | grep -v '\.gitkeep$'
  fail=1
else
  echo "OK: no data/raw or data/processed files currently tracked."
fi

if git ls-files | grep -E '(^|/)\.kaggle(/|$)|(^|/)\.env($|\.[A-Za-z0-9._-]*$)' | grep -q .; then
  echo "FAIL: credential-shaped files are tracked:"
  git ls-files | grep -E '(^|/)\.kaggle(/|$)|(^|/)\.env($|\.[A-Za-z0-9._-]*$)'
  fail=1
else
  echo "OK: no .kaggle/ or .env files tracked."
fi

echo
echo "== Scanning staged diff for credential-shaped strings =="
diff_content=$(git diff --cached)
pattern='(api[_-]?key|secret|token|password)["'"'"']?\s*[:=]\s*["'"'"'][A-Za-z0-9_\-]{16,}|kaggle\.json|AKIA[0-9A-Z]{16}'
if echo "$diff_content" | grep -qiE "$pattern"; then
  echo "FAIL: staged diff contains a credential-shaped string:"
  echo "$diff_content" | grep -inE "$pattern"
  fail=1
else
  echo "OK: no credential-shaped strings found in staged diff."
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "All checks passed. Safe to push."
else
  echo "One or more checks FAILED. Do not push until resolved."
fi
exit "$fail"
