# poem-chain-poc

Does a chain of skills hold together when the only thing crossing a step boundary
is a file on disk — and can you prove a step ran without believing its transcript?

Three skills, three separate `claude` processes, one file between each.

```
poem-writer ──01-poem.json──▶ poem-translator ──02-translation.json──▶ gist-publisher ──▶ 03-published.json
```

## The two rules being tested

**Isolation is structural, not instructional.** Each step is its own process with
its own context. Nothing is told to ignore the previous step — it structurally
cannot see it. If the chain works under those conditions, the handoff file is
provably the channel, because there is nothing else it could have been.

**A step ran if and only if its file exists.** `verify.py` decides from artifacts,
never from what a step said. It reports three strengths of evidence:

| | Means |
|---|---|
| `EXISTS` | the file is there, non-empty, parseable, correctly shaped |
| `CHAINED` | step N recorded the SHA-256 of step N−1's file, and it matches disk |
| `HONEST` | the model's claim agrees with the artifact |

`CHAINED` is the one that earns its keep. A step that invents its input passes
`EXISTS` and fails `CHAINED`. A step whose transcript says "published the gist"
while `03-published.json` is missing is reported as a **false claim**, which is
a worse outcome than an honest failure and does not look the same.

A step that ran and failed still writes its file, with `payload: null` and the
reason in `not_done`. Failing loudly and not running at all must be
distinguishable — that is the whole point.

## Run it

```bash
./run.sh
```

Publishing is **off by default**. Step 3 renders the Markdown and records
`"published": false` unless you opt in explicitly:

```bash
POC_PUBLISH=1 ./run.sh
```

Gists are created `--secret`, never `--public`. The chain is fully testable
without ever creating one.

```bash
python3 verify.py --selftest   # the verifier's own checks
python3 verify.py              # verdict on the current handoff/ contents
```

## Findings

### 1. `PreToolUse` matcher does take `Skill`

Matchers are compared against the tool name as an exact string (regex also
supported), not chosen from an approved list. The CLI validates them and warns
`Hook matcher \`X\` matches no tool (it is compared as an exact string)` for an
unknown one. `Skill` is a real registered tool — it appears in the session's own
tool list — so `matcher: "Skill"` is valid.

The published hooks page lists example matcher values and does not happen to
mention `Skill`. That is an omission from an example, not an exclusion.

### 2. The skill name IS in the payload, at `tool_input.skill`

The `PreToolUse` schema in the shipped binary (v2.1.246):

```
hook_event_name: "PreToolUse", tool_name: string, tool_input: object, tool_use_id: string
```

`tool_input` is the invoked tool's own parameter object, passed whole. The Skill
tool's parameters are `skill` and `args`, so the skill name arrives at
`tool_input.skill`. There is no dedicated `skill_name` field — asking for one and
concluding the name is unavailable is the wrong read.

Also present beyond the documented set: `PostToolUseFailure` and
`PermissionRequest` hook events.

**Verified from the schema, not yet observed firing.** `.claude/hooks/` carries
two probes that settle it on the first successful run: one on `matcher: "Skill"`,
and a catch-all control. If a Skill tool call shows up in `logs/all-tools.jsonl`
but nothing lands in `logs/skill-invocations.jsonl`, the specific matcher is what
failed — not the invocation. `verify.py` prints that comparison.

## Known blocker

Nested `claude -p` cannot authenticate on this machine right now:

```
Failed to authenticate: OAuth session expired and could not be refreshed
```

The keychain entry `Claude Code-credentials` exists but holds empty
`accessToken` and `refreshToken`, and `~/.claude/daemon-auth-status.json` reads
`{"status":"auth_required"}`. Log in interactively and re-run. Nothing about the
chain design depends on this.

## Traps already hit, so you don't

- **`--allowedTools` is variadic.** A trailing positional prompt gets swallowed as
  another tool name and the run dies with *"Input must be provided either through
  stdin or as a prompt argument"*. Send the prompt on stdin.
- **`--setting-sources project` breaks auth.** It drops the user settings carrying
  credentials, and every step fails with the OAuth message above — which reads as
  a credentials problem and is a flag problem. Isolation does not need it; the
  process boundary already provides it.
- **`--output-format json` returns either a result object or an array of messages**
  ending in one, depending on which settings loaded. `verify.py` handles both.

## Limitation

Without `--setting-sources project`, each step also loads your user-level plugins
and global settings. That is cosmetic noise in the step's own context, not
cross-step influence — the process boundary still holds. If you need that closed
too, pass an explicit `--settings` file instead of dropping the source entirely.
