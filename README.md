# poem-chain-poc

Does a chain of skills hold together when the only thing crossing a step
boundary is a file on disk — and can you prove a step ran without believing its
transcript?

```
--theme --lang ─▶ 00-request.json ─▶ poem-writer ─▶ 01-poem.json ─▶ poem-translator
      ─▶ 02-translation.json ─▶ gist-publisher ─▶ 03-published.json + one named gist
```

Three skills, three separate `claude` processes, one file between each.

## The two rules

**Isolation is structural, not instructional.** Each step is its own process
with its own context. Nothing is told to ignore the previous step — it
structurally cannot see it, so the handoff file is provably the channel. The
`--theme` and `--lang` flags travel the same way, as `00-request.json`, rather
than as environment variables a step cannot read anyway (finding 3).

**A step ran if and only if its file exists.** `verify.py` decides from
artifacts, never from what a step said:

| | Means |
|---|---|
| `EXISTS` | the file is there, non-empty, parseable, correctly shaped |
| `CHAINED` | step N recorded the SHA-256 of step N−1's file, and it matches disk |
| `HONEST` | the model's claim agrees with the artifact |
| `ASKED` | the `--theme` and `--lang` that went in are what came back out |
| `SERVED` | the gist serves back the exact bytes of `handoff/poem.md` |

Each catches a different lie. A step that invents its input passes `EXISTS` and
fails `CHAINED`. A transcript claiming a publish with no `03-published.json` is
reported as a **false claim** — worse than an honest failure, and it must not
look the same. A recorded `gist_url` is still only a claim, so `SERVED` needs
network and is a separate invocation.

A step that ran and failed still writes its file, `payload: null` and the reason
in `not_done`. Failing loudly and never running must be distinguishable.

## Run it

```bash
./run.sh
./run.sh --theme "a lighthouse keeper counting ships that never come" --lang Japanese
```

| | |
|---|---|
| `-t, --theme` | subject of the poem. Omit and step 1 picks its own. |
| `-l, --lang` | what step 2 translates into, default `pt-BR`. A name, a tag, anything — echoed back verbatim so `verify.py` can check what arrived. |
| `--keep` | do not wipe `handoff/` and `logs/` first. |

**Step 3 publishes on every run.** There is no opt-in flag.

```bash
python3 verify.py --selftest      # the verifier's own checks, no network
python3 verify.py                 # verdict on the current handoff/ contents
python3 verify.py --check-gist    # network: does the gist serve this run's poem?
```

`./run.sh` runs the latter two and exits non-zero if either fails.

## The gist

Step 3 **updates one gist that already exists** —
[`82d5937c…74bd3`](https://gist.github.com/GoldenMaximo/82d5937c2bd01d9ade230e3722074bd3),
named in `.claude/skills/gist-publisher/SKILL.md`. It never creates one, never
deletes one, never removes a file from one.

```bash
gh gist edit 82d5937c2bd01d9ade230e3722074bd3 --add handoff/poem.md
```

`--add` names the file by its basename and replaces it if already present, so
the command is idempotent and every other file in the gist is untouched.

**That gist is public**, so the poem is world-readable — the trade for
publishing to a handed-over target instead of one this repo controls. An earlier
version created its own with `--secret`; a gist you were handed already had its
visibility decided. Step 3 therefore sets none: it reads what the gist actually
is off the API and records that, and `--check-gist` warns when it is public.

## Findings

**1. `PreToolUse` matcher does take `Skill`.** Matchers are compared against the
tool name as an exact string (regex also works), not chosen from an approved
list — the CLI warns ``Hook matcher `X` matches no tool`` for an unknown one.
`Skill` is a real registered tool, so `matcher: "Skill"` is valid. The published
hooks page just doesn't happen to use it as an example.

**2. The skill name is in the payload, at `tool_input.skill`.** Schema in the
shipped binary (v2.1.246): `hook_event_name`, `tool_name`, `tool_input`,
`tool_use_id`. `tool_input` is the invoked tool's own parameter object passed
whole, and the Skill tool's parameters are `skill` and `args` — there is no
separate `skill_name` field, and concluding from its absence that the name is
unavailable is the wrong read. Also undocumented: the `PostToolUseFailure` and
`PermissionRequest` events.

Observed, not just read off the schema: two probes (one on `matcher: "Skill"`,
one catch-all control) captured three payloads across three steps. They are
deleted now that they've answered — and the control was misleading anyway, since
`*` logs any other session working in this directory. Restore from git history
to re-confirm against a future CLI.

**3. A step under `--allowedTools` cannot read an environment variable.** This
cost a whole run. Step 3 gated publishing on `POC_PUBLISH` and reported:

```
POC_PUBLISH not verifiable as 1 (environment reads denied:
printenv/env/python os.environ all refused approval); default applies
```

`--allowedTools` is an allowlist of *commands*, and `printenv`, `env` and
`python3 -c "os.environ"` are not among the granted ones. A skill saying "check
the environment variable X" is unimplementable unless you also grant
`Bash(printenv:*)` — and it fails silently and politely, taking the documented
default and reporting clean success. So everything a step must *decide* from now
lives in its skill file or its input file. `GH_TOKEN` is the exception that
proves the rule: `gh` reads it, the model never has to.

## Traps already hit, so you don't

- **`--allowedTools` is variadic.** A trailing positional prompt gets eaten as
  another tool name: *"Input must be provided either through stdin or as a prompt
  argument"*. Send the prompt on stdin.
- **`--setting-sources project` breaks auth.** It drops the user settings that
  carry credentials, so every step dies with *"OAuth session expired"* — reads
  like a credentials problem, is a flag problem. The process boundary already
  provides the isolation.
- **`--output-format json` returns a result object or an array of messages
  ending in one**, depending on which settings loaded. `verify.py` handles both.
- **`HTTP 403: Rate Limit Exceeded` from `gh` is usually the wrong account.**
  With two accounts logged in `gh` uses the *active* one, and an
  enterprise-managed account gets 403 on an ordinary gist while `gh api
  rate_limit` reports 5000 remaining. `run.sh` pins
  `GH_TOKEN=$(gh auth token --user "$POC_GIST_ACCOUNT")` instead of
  `gh auth switch`, which would change the active account globally.
- **`gh gist edit` is non-interactive only if you give it a source file.** With
  just an id it opens `$EDITOR` and hangs a `--print` run forever.
- **Don't diff against `gh ... --jq '.files[].content'`.** `--jq` appends a
  newline, so identical files compare unequal. `verify.py` parses the JSON and
  compares the `content` string's UTF-8 bytes.

## Limitation

Each step also loads your user-level plugins and global settings. Cosmetic noise
in the step's own context, not cross-step influence — the process boundary still
holds. To close that too, pass an explicit `--settings` file rather than
dropping `--setting-sources`.
