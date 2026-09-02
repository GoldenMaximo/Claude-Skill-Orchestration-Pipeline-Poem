---
name: gist-publisher
description: Step 3 of the handoff chain. Reads handoff/02-translation.json, renders both poems to Markdown, publishes them to one named GitHub gist, and records the result in handoff/03-published.json. Trigger on "publish the gist", "run step 3", "gist-publisher".
---

# gist-publisher — step 3 of 3

You consume exactly one file and produce exactly one file, and you publish.

| | |
|---|---|
| Consumes | `handoff/02-translation.json` |
| Produces | `handoff/03-published.json`, `handoff/poem.md` |
| Publishes to | gist `82d5937c2bd01d9ade230e3722074bd3`, file `poem.md` |

## Scope

**In scope:** rendering the translated poem to Markdown and updating the one gist
named above.

**Out of scope:** writing or editing a poem, re-translating, creating a new gist,
reading any file other than your input, publishing anything that is not in your
input file.

## You update one gist. You never create one.

The target is fixed and written above: `82d5937c2bd01d9ade230e3722074bd3`. You
add or replace one file inside it, `poem.md`. You do not create gists, you do not
delete gists, and you do not remove files from one.

The id is written here in this file, not passed in the environment, and that is
deliberate. You run under `--allowedTools`, so `printenv`, `env` and
`python -c "os.environ"` are all denied to you — a step that has to read an
environment variable to know what to do cannot do it. Anything you must *decide*
from lives in this file or in your input file. The environment still carries
`GH_TOKEN` for `gh` itself to use; that works because `gh` reads it, not you.

## Publishing is unconditional

There is no opt-in flag and nothing to check first. Every run of this step
updates the gist. If the update fails, you record the failure — you do not treat
"did not publish" as a normal outcome.

## What to do

1. Read `handoff/02-translation.json`.
   - If it does not exist, write `handoff/03-published.json` with `payload: null`
     and the reason in `not_done`, and stop. Do not invent an input.
2. Compute the SHA-256 of the input file: `shasum -a 256 handoff/02-translation.json`
3. Render `handoff/poem.md` from `payload`, entirely from your input file:

```markdown
# <payload.title>

<payload.lines, one per line>

---

## Original

# <payload.source_title>

<payload.source_lines, one per line>
```

If `source_lines` is missing from your input, render the title alone and put
`"input carried no source_lines; ## Original holds the title only"` in
`not_done`. Do not go read step 1's file to fill the gap — it is not your input.

4. Update the gist:

```bash
gh gist edit 82d5937c2bd01d9ade230e3722074bd3 --add handoff/poem.md
```

`--add` names the file by its basename, `poem.md`, and replaces that file's
contents if it is already there — so re-running is safe and does not pile up
copies. Every other file in the gist is left alone.

5. Compute the SHA-256 of the rendered Markdown too:
   `shasum -a 256 handoff/poem.md`. This is what `verify.py --check-gist`
   compares against what the gist actually serves back.
6. Read the gist's real visibility rather than assuming it:

```bash
gh api gists/82d5937c2bd01d9ade230e3722074bd3 --jq 'if .public then "public" else "secret" end'
```

7. Write `handoff/03-published.json`:

```json
{
  "step": 3,
  "skill": "gist-publisher",
  "produced_at": "<UTC ISO-8601>",
  "input_file": "handoff/02-translation.json",
  "input_sha256": "<the hash from step 2 above>",
  "payload": {
    "published": true,
    "gist_id": "82d5937c2bd01d9ade230e3722074bd3",
    "gist_url": "https://gist.github.com/GoldenMaximo/82d5937c2bd01d9ade230e3722074bd3",
    "gist_file": "poem.md",
    "visibility": "<what step 6 actually printed>",
    "markdown_path": "handoff/poem.md",
    "markdown_sha256": "<the hash from step 5>"
  },
  "not_done": []
}
```

8. Reply with one sentence naming the file you wrote and the gist URL. Nothing else.

## Rules

- `input_sha256` is the proof you read your input. Run the command; never guess.
- Never create a gist. Never delete a gist. Never remove a file from one.
- Never pass `--public`. You are not setting visibility at all — you are writing
  into a gist whose visibility was already decided by whoever made it. Report
  what step 6 printed, not what would be reassuring.
- If `gh` fails, record `"published": false`, put the exact error in `not_done`,
  and still write the file. A step that ran and failed must be distinguishable
  from a step that never ran.
