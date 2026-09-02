---
name: poem-translator
description: Step 2 of the handoff chain. Reads handoff/01-poem.json and writes a translation into the language that file requests to handoff/02-translation.json. Trigger on "translate the poem", "run step 2", "poem-translator".
---

# poem-translator — step 2 of 3

You consume exactly one file and produce exactly one file.

| | |
|---|---|
| Consumes | `handoff/01-poem.json` |
| Produces | `handoff/02-translation.json` |

## Scope

**In scope:** translating the poem in your input file into the language that same
file asks for.

**Out of scope:** writing a new poem, improving the English, publishing anything,
reading any file other than your input, choosing the target language yourself.
If the poem is bad, translate it anyway — judging it is not your job.

## The target language comes from your input file

`payload.target_language` in `handoff/01-poem.json` is the language to translate
into. It was copied there by step 1 from the run request, because you consume
exactly one file and cannot go read the request yourself.

It may be a name (`Japanese`), a tag (`pt-BR`), or anything else the operator
typed. Translate into whatever it denotes, and echo the string back in
`payload.language` **verbatim** — `verify.py` compares that field against what
was asked for, so normalising `Japanese` to `ja` reads as the wrong language.

If `target_language` is missing or empty, translate into Brazilian Portuguese,
set `payload.language` to `pt-BR`, and record the substitution in `not_done`.

## What to do

1. Read `handoff/01-poem.json`.
   - **If it does not exist, stop.** Write `handoff/02-translation.json` with
     `payload: null` and `not_done: ["input file handoff/01-poem.json not found"]`,
     then say so. Do not invent an input.
2. Compute the SHA-256 of the input file, exactly as it is on disk:
   `shasum -a 256 handoff/01-poem.json`
3. Translate `payload.lines` into `payload.target_language`, line for line. Keep
   the same number of lines. Translate the title too.
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
    "language": "<target_language from your input, verbatim>",
    "lines": ["<translated line 1>", "..."],
    "source_title": "<original title>",
    "source_lines": ["<original line 1>", "..."]
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
- `source_title` and `source_lines` are the original English, copied through
  verbatim. Step 3 consumes only your file, so anything you drop here is gone
  from the chain -- it cannot go back and read step 1's file to recover it.
- Never write outside `handoff/02-translation.json`.
