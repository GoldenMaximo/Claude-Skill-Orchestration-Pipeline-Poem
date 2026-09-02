---
name: poem-writer
description: Step 1 of the handoff chain. Reads the run request in handoff/00-request.json and writes an original short English poem on the requested subject to handoff/01-poem.json. Trigger on "write the poem", "run step 1", "poem-writer".
---

# poem-writer — step 1 of 3

You consume exactly one file and produce exactly one file.

| | |
|---|---|
| Consumes | `handoff/00-request.json` |
| Produces | `handoff/01-poem.json` |

## Scope

**In scope:** writing an original short poem in English (8–16 lines) on the
subject named in your input file.

**Out of scope:** translating it, publishing it, editing any other file, reading
any other handoff file, choosing your own subject when one was given to you.

## Your subject comes from a file, not from the prompt

`handoff/00-request.json` is written by `run.sh` from its command-line flags:

```json
{ "theme": "<the subject to write about, or null>", "target_language": "<for step 2>" }
```

The request arrives as a file for the same reason every other handoff does: you
run under `--allowedTools`, so `printenv` and `env` are denied to you and an
environment variable is not something you can read. A file is.

- **`theme` is a non-empty string** — write about that. It is the whole point of
  the run; do not substitute a subject you like better.
- **`theme` is `null`, missing, or the file does not exist** — choose your own
  subject and record `"theme": null` in your payload. This is a normal run, not
  a failure. If the file is missing entirely, say so in `not_done` as well.

`target_language` is not yours to act on. Copy it through untouched so step 2
receives it — step 2 consumes only your file and cannot go read the request
itself.

## What to do

1. Read `handoff/00-request.json`.
2. Compute its SHA-256: `shasum -a 256 handoff/00-request.json`
   - If the file does not exist, use `null` for both `input_file` and
     `input_sha256`. Never guess a hash.
3. Write an original short poem in English on the requested subject. Give it a title.
4. Write `handoff/01-poem.json` with exactly this shape:

```json
{
  "step": 1,
  "skill": "poem-writer",
  "produced_at": "<UTC ISO-8601, e.g. 2026-08-27T14:03:11Z>",
  "input_file": "handoff/00-request.json",
  "input_sha256": "<the hash from step 2 above>",
  "payload": {
    "title": "<poem title>",
    "language": "en",
    "lines": ["<line 1>", "<line 2>", "..."],
    "theme": "<the theme you were given, verbatim, or null>",
    "target_language": "<target_language from the request, verbatim>"
  },
  "not_done": []
}
```

5. Reply with one sentence naming the file you wrote. Nothing else.

## Rules

- `lines` is an array of strings, one per line of the poem. Do not embed `\n`.
- `input_sha256` is the proof you read the request. Run the command; never guess.
- `theme` and `target_language` are echoed back verbatim so the run is checkable:
  `verify.py` compares them against what was actually asked for. Paraphrasing the
  theme or normalising the language string reads as the parameter not arriving.
- If you cannot complete the poem for any reason, still write the file, set
  `payload` to `null`, and put the reason in `not_done` as a string. A missing
  file means the step did not run; a file saying what failed is a step that ran
  and reported honestly. Those are different outcomes and must look different.
- Never write outside `handoff/01-poem.json`.
