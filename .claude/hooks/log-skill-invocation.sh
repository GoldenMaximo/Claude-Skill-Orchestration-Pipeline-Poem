#!/usr/bin/env bash
# PreToolUse hook, matcher "Skill". Appends the RAW payload, unmodified, so the
# first run answers two questions empirically:
#   1. does a matcher of "Skill" actually fire?          -> this file is non-empty
#   2. is the skill name in the payload, and where?      -> read tool_input
# Never blocks: always exits 0.
set -u
DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
mkdir -p "$DIR/logs"
cat >> "$DIR/logs/skill-invocations.jsonl"
printf '\n' >> "$DIR/logs/skill-invocations.jsonl"
exit 0
