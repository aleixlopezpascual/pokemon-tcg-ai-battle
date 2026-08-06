#!/usr/bin/env bash
cmd=$(jq -r '.tool_input.command // empty')

if echo "$cmd" | grep -qE '\bgit[[:space:]]+(add|commit)\b'; then
  if echo "$cmd" | grep -qE 'data/(raw|processed)'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: command references data/raw or data/processed. Kaggle competition data must never be committed (this repo will go public)."}}'
    exit 0
  fi
  if echo "$cmd" | grep -qE 'git[[:space:]]+add[[:space:]]+(-A|--all|\.)([[:space:]]|$)'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: broad git add (-A/--all/.) could stage data/raw or data/processed. Stage specific files instead."}}'
    exit 0
  fi
fi

echo '{}'
