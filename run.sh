#!/usr/bin/env bash
# Chain three skills across three SEPARATE claude processes.
#
# Isolation is structural, not instructional: each step is its own process with
# its own context. The only thing that crosses a step boundary is a file on disk.
# If the chain works under those conditions, the handoff file is provably the
# channel -- there is nothing else it could have been.
#
#   POC_PUBLISH=1 ./run.sh     also create a secret gist in step 3
#   KEEP=1 ./run.sh            do not wipe handoff/ and logs/ first
set -uo pipefail
cd "$(dirname "$0")"

if [ "${KEEP:-0}" != "1" ]; then
  rm -f handoff/*.json handoff/*.md logs/*.json logs/*.jsonl 2>/dev/null
fi
mkdir -p handoff logs

# Isolation here is the process boundary, nothing else. Do NOT add
# --setting-sources project: it drops the user settings that carry auth, and every
# step dies with "OAuth session expired and could not be refreshed" -- which reads
# like a credentials problem and is actually a flag problem. Verified 2026-08-27.
COMMON=(--print --output-format json --permission-mode acceptEdits)

step () {
  local n="$1" tools="$2" prompt="$3"
  echo "── step $n ─────────────────────────────────────────────"
  # Prompt goes via stdin: --allowedTools is variadic, so a trailing positional
  # prompt gets swallowed as another tool name and the run dies with
  # "Input must be provided either through stdin or as a prompt argument".
  printf '%s' "$prompt" | claude "${COMMON[@]}" --allowedTools "$tools" \
    > "logs/step$n.json" 2> "logs/step$n.stderr"
  local rc=$?
  echo "   exit $rc · claimed: $(python3 verify.py --claim "$n" 2>/dev/null)"
  return 0
}

step 1 "Read Write" \
  "Invoke the poem-writer skill and follow it exactly."

step 2 "Read Write Bash(shasum:*)" \
  "Invoke the poem-translator skill and follow it exactly."

step 3 "Read Write Bash(shasum:*) Bash(gh gist create:*)" \
  "Invoke the gist-publisher skill and follow it exactly."

echo
python3 verify.py
