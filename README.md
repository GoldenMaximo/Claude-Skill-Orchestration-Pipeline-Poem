# poem-chain-poc

Does a chain of skills hold together when the only thing crossing a step boundary
is a file on disk — and can you prove a step ran without believing its transcript?

Three skills, three separate `claude` processes, one file between each.

```
poem-writer ──01-poem.json──▶ poem-translator ──02-translation.json──▶ gist-publisher ──▶ 03-published.json
                                                                             │
                                                                             └─▶ one named gist, file poem.md
```

## The two rules being tested

**Isolation is structural, not instructional.** Each step is its own process with
its own context. Nothing is told to ignore the previous step — it structurally
cannot see it. If the chain works under those conditions, the handoff file is
provably the channel, because there is nothing else it could have been.

**A step ran if and only if its file exists.** `verify.py` decides from artifacts,
never from what a step said. It reports four strengths of evidence:

| | Means |
|---|---|
| `EXISTS` | the file is there, non-empty, parseable, correctly shaped |
| `CHAINED` | step N recorded the SHA-256 of step N−1's file, and it matches disk |
| `HONEST` | the model's claim agrees with the artifact |
| `SERVED` | the gist actually serves back the exact bytes of `handoff/poem.md` |

`CHAINED` is the one that earns its keep locally. A step that invents its input
passes `EXISTS` and fails `CHAINED`. A step whose transcript says "published the
gist" while `03-published.json` is missing is reported as a **false claim**,
which is a worse outcome than an honest failure and does not look the same.

`SERVED` is the same rule pointed at the network, and it is the only check that
can tell a real publish from a recorded `gist_url`. A URL in a JSON file is a
claim like any other; the evidence is the remote content matching the local
render byte for byte. It needs network, so it is opt-in.

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

```bash
python3 verify.py --selftest      # the verifier's own checks, no network
python3 verify.py                 # verdict on the current handoff/ contents
python3 verify.py --check-gist    # network: does the gist serve this run's poem?
```

## The gist step 3 writes into

Step 3 **updates one gist that already exists**. It never creates one, never
deletes one, and never removes a file from one. The target is
[`82d5937c2bd01d9ade230e3722074bd3`](https://gist.github.com/GoldenMaximo/82d5937c2bd01d9ade230e3722074bd3),
set in `run.sh` and passed to the step as `POC_GIST_ID`.

```bash
gh gist edit "$POC_GIST_ID" --add handoff/poem.md
```

`--add` names the file by its basename, `poem.md`, and replaces that file's
contents when it is already present — so the command is idempotent and does not
accumulate copies. Any other file in the gist is untouched.

Point it somewhere else with the two overrides:

```bash
POC_GIST_ID=<other id> POC_GIST_ACCOUNT=<owner> POC_PUBLISH=1 ./run.sh
```

**That gist is public.** An earlier version of this POC created its own gist with
`--secret`; updating a gist you were handed is a different act, and the
visibility was already decided by whoever made it. Step 3 therefore does not set
visibility at all — it reads what the gist actually is off the API and records
that, and `verify.py --check-gist` prints a `WARN` when the answer is public.
The poem in that gist is world-readable. That is the deliberate trade for
publishing to a named target instead of one this repo controls.

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

Note that the catch-all probe also logs the tool calls of any *other* session
working in this directory, this one included, so a non-zero count in
`all-tools.jsonl` is not by itself evidence that a chain step ran.

## Traps already hit, so you don't

- **`--allowedTools` is variadic.** A trailing positional prompt gets swallowed as
  another tool name and the run dies with *"Input must be provided either through
  stdin or as a prompt argument"*. Send the prompt on stdin.
- **`--setting-sources project` breaks auth.** It drops the user settings carrying
  credentials, and every step fails with *"OAuth session expired and could not be
  refreshed"* — which reads as a credentials problem and is a flag problem.
  Isolation does not need it; the process boundary already provides it.
- **`--output-format json` returns either a result object or an array of messages**
  ending in one, depending on which settings loaded. `verify.py` handles both.
- **`HTTP 403: Rate Limit Exceeded` from `gh` is usually the wrong account, not
  the rate.** With two accounts logged in, `gh` uses the *active* one; an
  enterprise-managed (EMU) account gets 403 on an ordinary github.com gist while
  `gh api rate_limit` cheerfully reports 5000 remaining. `run.sh` pins
  `GH_TOKEN=$(gh auth token --user "$POC_GIST_ACCOUNT")` for step 3 rather than
  running `gh auth switch`, which would change the active account globally.
- **`gh gist edit` is only non-interactive if you give it a source file.** With
  just an id it opens `$EDITOR` and hangs a `--print` run forever. The second
  positional argument (or `-a/--add`) is the local file it reads instead.
- **Don't compare against `gh ... --jq '.files[].content'`.** `--jq` appends a
  newline, so a byte-for-byte comparison fails on a file that is in fact
  identical. `verify.py` parses the JSON and compares the `content` string's
  UTF-8 bytes.

## Limitation

Without `--setting-sources project`, each step also loads your user-level plugins
and global settings. That is cosmetic noise in the step's own context, not
cross-step influence — the process boundary still holds. If you need that closed
too, pass an explicit `--settings` file instead of dropping the source entirely.
