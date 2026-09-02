#!/usr/bin/env bash
# Chain three skills across three SEPARATE claude processes.
#
# Isolation is structural, not instructional: each step is its own process with
# its own context. The only thing that crosses a step boundary is a file on disk.
# If the chain works under those conditions, the handoff file is provably the
# channel -- there is nothing else it could have been.
#
# Step 3 publishes on every run. There is no opt-in flag.
#
# Usage:
#   ./run.sh [-t|--theme SUBJECT] [-l|--lang LANGUAGE] [--keep]
#
#   ./run.sh -t "a lighthouse in winter" -l Japanese
set -uo pipefail
cd "$(dirname "$0")"

THEME=""
LANG_TARGET="pt-BR"
KEEP=0

usage () {
  cat <<'USAGE'
Usage: ./run.sh [-t|--theme SUBJECT] [-l|--lang LANGUAGE] [--keep]

  -t, --theme  what the poem is about. Omit to let step 1 choose.
  -l, --lang   what step 2 translates into. Default pt-BR. A name
               ("Japanese"), a tag ("ja"), anything -- it is echoed back
               verbatim so verify.py can check the language that arrived.
      --keep   do not wipe handoff/ and logs/ first.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    -t|--theme) [ $# -ge 2 ] || { echo "$1 needs a value" >&2; exit 2; }
                THEME="$2"; shift 2 ;;
    -l|--lang)  [ $# -ge 2 ] || { echo "$1 needs a value" >&2; exit 2; }
                LANG_TARGET="$2"; shift 2 ;;
    --keep)     KEEP=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$LANG_TARGET" ] || { echo "--lang cannot be empty" >&2; exit 2; }

# The gist id lives in .claude/skills/gist-publisher/SKILL.md, NOT here and NOT
# in the environment. Under --allowedTools a step cannot run printenv/env, so it
# cannot read an environment variable at all -- anything a step must *decide*
# from has to be in its skill file or its input file. That is why --theme and
# --lang below become handoff/00-request.json instead of exported variables.
# GH_TOKEN is the exception that proves the rule: `gh` reads it, the model never
# has to.
POC_GIST_ACCOUNT="${POC_GIST_ACCOUNT:-GoldenMaximo}"

# The gist is owned by POC_GIST_ACCOUNT. If gh's *active* account is a different
# one -- an enterprise-managed (EMU) account, say -- every call for this gist
# comes back "HTTP 403: Rate Limit Exceeded" while `gh api rate_limit` reports a
# full 5000 remaining. That message is about the account, not the rate. Pin the
# token for the owning account instead of `gh auth switch`, which would change
# the active account globally. Exported before the steps so both step 3 and the
# closing remote check see it.
if GH_TOKEN="$(gh auth token --user "$POC_GIST_ACCOUNT" 2>/dev/null)" && [ -n "$GH_TOKEN" ]; then
  export GH_TOKEN
else
  echo "!! no gh token for '$POC_GIST_ACCOUNT'; step 3 will record the failure"
fi

if [ "$KEEP" != "1" ]; then
  rm -f handoff/*.json handoff/*.md logs/*.json logs/*.jsonl logs/*.stderr 2>/dev/null
fi
mkdir -p handoff logs

# The run request is an artifact like every other handoff, so what was ASKED for
# is on disk next to what came back and verify.py can compare the two. Built with
# python, not printf, so a theme containing quotes or backslashes stays valid JSON.
THEME="$THEME" LANG_TARGET="$LANG_TARGET" python3 -c '
import json, os
theme = os.environ["THEME"]
json.dump({"theme": theme or None,
           "target_language": os.environ["LANG_TARGET"]},
          open("handoff/00-request.json", "w"), ensure_ascii=False, indent=2)
' || { echo "could not write handoff/00-request.json" >&2; exit 1; }

echo "request · theme: ${THEME:-<step 1 chooses>} · language: $LANG_TARGET"

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
  #
  # The prompt is identical on every run and carries no parameters. The theme and
  # the language reach the steps through handoff/00-request.json, so the file is
  # provably the channel for those too -- same rule as the rest of the chain.
  printf '%s' "$prompt" | claude "${COMMON[@]}" --allowedTools "$tools" \
    > "logs/step$n.json" 2> "logs/step$n.stderr"
  local rc=$?
  echo "   exit $rc · claimed: $(python3 verify.py --claim "$n" 2>/dev/null)"
  return 0
}

step 1 "Read Write Bash(shasum:*)" \
  "Invoke the poem-writer skill and follow it exactly."

step 2 "Read Write Bash(shasum:*)" \
  "Invoke the poem-translator skill and follow it exactly."

step 3 "Read Write Bash(shasum:*) Bash(gh gist edit:*) Bash(gh api:*)" \
  "Invoke the gist-publisher skill and follow it exactly."

echo
python3 verify.py
local_rc=$?
echo
python3 verify.py --check-gist
remote_rc=$?
[ "$local_rc" -eq 0 ] && [ "$remote_rc" -eq 0 ]
