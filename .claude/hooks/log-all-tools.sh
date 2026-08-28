#!/usr/bin/env bash
# Control for the "Skill" matcher test. Matcher "*" sees every tool call, so if a
# Skill tool_use appears here but NOT in skill-invocations.jsonl, the specific
# matcher is the thing that failed -- not the skill invocation.
# Records tool_name only, to stay small. Never blocks.
set -u
DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
mkdir -p "$DIR/logs"
python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print(json.dumps({"tool_name": d.get("tool_name"), "tool_use_id": d.get("tool_use_id")}))
' >> "$DIR/logs/all-tools.jsonl" 2>/dev/null
exit 0
