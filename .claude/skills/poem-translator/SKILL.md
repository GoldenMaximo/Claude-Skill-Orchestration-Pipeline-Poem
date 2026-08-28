---
name: poem-translator
description: Step 2 of the handoff chain. Reads handoff/01-poem.json and writes a Brazilian Portuguese translation to handoff/02-translation.json. Trigger on "translate the poem", "run step 2", "poem-translator".
---

# poem-translator — step 2 of 3

You consume exactly one file and produce exactly one file.

| | |
|---|---|
| Consumes | `handoff/01-poem.json` |
| Produces | `handoff/02-translation.json` |

## Scope

**In scope:** translating the poem in your input file into Brazilian Portuguese.

**Out of scope:** writing a new poem, improving the English, publishing anything,
reading any file other than your input. If the poem is bad, translate it anyway —
judging it is not your job.

## What to do

1. Read `handoff/01-poem.json`.
   - **If it does not exist, stop.** Write `handoff/02-translation.json` with
     `payload: null` and `not_done: ["input file handoff/01-poem.json not found"]`,
     then say so. Do not invent an input.
2. Compute the SHA-256 of the input file, exactly as it is on disk:
   `shasum -a 256 handoff/01-poem.json`
3. Translate `payload.lines` into Brazilian Portuguese, line for line. Keep the
   same number of lines. Translate the title too.
4. Write `handoff/02-translation.json`:

```json
{
  "step": 2,
  "skill": "poem-translator",
  "produced_at": "<UTC ISO-8601>",
  "input_file": "handoff/01-poem.json",
  "input_sha256": "<the hash from step 2 above>",
  "payload": {
    "title": "<translated title>",
    "language": "pt-BR",
    "lines": ["<translated line 1>", "..."],
    "source_title": "<original title>"
  },
  "not_done": []
}
```

5. Reply with one sentence naming the file you wrote. Nothing else.

## Rules

- `input_sha256` is the proof you actually read your input. Never guess it,
  never copy it from anywhere, never leave it null when the input existed.
  Run the command.
- Line count of `payload.lines` must equal the input's line count. If you cannot
  hold that, say which lines you dropped in `not_done`.
- Never write outside `handoff/02-translation.json`.
