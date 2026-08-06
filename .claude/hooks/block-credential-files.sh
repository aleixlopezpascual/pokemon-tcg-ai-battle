#!/usr/bin/env bash
file=$(jq -r '.tool_input.file_path // empty')

if echo "$file" | grep -qE '(^|/)\.kaggle(/|$)' || echo "$file" | grep -qE '(^|/)\.env($|\.[A-Za-z0-9._-]*$)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: this path holds credentials (.kaggle/ or .env). This repo will go public - credentials must never be read, edited, or written here."}}'
  exit 0
fi

echo '{}'
