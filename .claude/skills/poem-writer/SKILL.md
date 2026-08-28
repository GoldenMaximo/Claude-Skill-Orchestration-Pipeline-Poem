---
name: poem-writer
description: Step 1 of the handoff chain. Writes an original short poem in English and records it in handoff/01-poem.json. Trigger on "write the poem", "run step 1", "poem-writer".
---

# poem-writer — step 1 of 3

You produce one artifact and nothing else: `handoff/01-poem.json`.

## Scope

**In scope:** writing an original short poem in English (8–16 lines).

**Out of scope:** translating it, publishing it, editing any other file, reading
any other handoff file. Step 1 has no input file — it is the head of the chain.

## What to do

1. Write an original short poem in English. Any subject. Give it a title.
2. Write `handoff/01-poem.json` with exactly this shape:

```json
{
  "step": 1,
  "skill": "poem-writer",
  "produced_at": "<UTC ISO-8601, e.g. 2026-08-27T14:03:11Z>",
  "input_file": null,
  "input_sha256": null,
  "payload": {
    "title": "<poem title>",
    "language": "en",
    "lines": ["<line 1>", "<line 2>", "..."]
  },
  "not_done": []
}
```

3. Reply with one sentence naming the file you wrote. Nothing else.

## Rules

- `lines` is an array of strings, one per line of the poem. Do not embed `\n`.
- If you cannot complete the poem for any reason, still write the file, set
  `payload` to `null`, and put the reason in `not_done` as a string. A missing
  file means the step did not run; a file saying what failed is a step that ran
  and reported honestly. Those are different outcomes and must look different.
- Never write outside `handoff/01-poem.json`.
