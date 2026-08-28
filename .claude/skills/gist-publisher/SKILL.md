---
name: gist-publisher
description: Step 3 of the handoff chain. Reads handoff/02-translation.json and publishes both poems as a secret GitHub gist, recording the result in handoff/03-published.json. Trigger on "publish the gist", "run step 3", "gist-publisher".
---

# gist-publisher — step 3 of 3

You consume exactly one file and produce exactly one file.

| | |
|---|---|
| Consumes | `handoff/02-translation.json` |
| Produces | `handoff/03-published.json` |

## Scope

**In scope:** rendering the translated poem to Markdown and, when publishing is
enabled, creating one secret gist.

**Out of scope:** writing or editing a poem, re-translating, publishing anything
that is not in your input file.

## Publishing is off unless explicitly enabled

Check the environment variable `POC_PUBLISH`.

- **`POC_PUBLISH` is not `1`** — this is the default. Render the Markdown,
  write your handoff file with `"published": false` and
  `not_done: ["POC_PUBLISH not set; gist not created"]`, and stop. This is a
  successful run of the step, not a failure. The chain is fully testable
  without ever creating a gist.
- **`POC_PUBLISH=1`** — create the gist, secret, with the command below exactly.

## What to do

1. Read `handoff/02-translation.json`.
   - If it does not exist, write `handoff/03-published.json` with `payload: null`
     and the reason in `not_done`. Do not invent an input.
2. Compute the SHA-256 of the input file: `shasum -a 256 handoff/02-translation.json`
3. Render a Markdown document to `handoff/poem.md`: the translated title as an
   `#` heading, the translated lines, then a `---`, then the original title and
   lines under an `## Original` heading.
4. If and only if `POC_PUBLISH=1`, run:

```bash
gh gist create handoff/poem.md --secret --desc "poem-chain-poc"
```

The gist is **secret** — never pass `--public`. Capture the URL it prints.

5. Write `handoff/03-published.json`:

```json
{
  "step": 3,
  "skill": "gist-publisher",
  "produced_at": "<UTC ISO-8601>",
  "input_file": "handoff/02-translation.json",
  "input_sha256": "<the hash from step 2 above>",
  "payload": {
    "published": true,
    "gist_url": "<url, or null when not published>",
    "visibility": "secret",
    "markdown_path": "handoff/poem.md"
  },
  "not_done": []
}
```

6. Reply with one sentence naming the file you wrote, and the gist URL if there
   is one. Nothing else.

## Rules

- `input_sha256` is the proof you read your input. Run the command; never guess.
- Never create a public gist. Never delete a gist.
- If `gh` fails, record `"published": false`, put the exact error in `not_done`,
  and still write the file. A step that ran and failed must be distinguishable
  from a step that never ran.
