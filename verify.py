#!/usr/bin/env python3
"""Decide whether each step ran, from its artifact -- never from what it said.

The rule this enforces: if step 3 did not produce its file, step 3 did not run.
A transcript saying "published the gist" is a claim, and a claim is not evidence.

Three checks, in increasing strength:

  EXISTS   the handoff file is there, non-empty, parseable, correctly shaped.
  CHAINED  step N records the SHA-256 of step N-1's file, and it matches the
           file actually on disk. This is what separates "step 3 ran" from
           "step 3 ran and actually read step 2" -- a step that invents its
           input passes EXISTS and fails CHAINED.
  HONEST   the model's own claim agrees with the artifact. A run that says it
           succeeded while its file is missing is reported as a false claim,
           which is a worse outcome than an honest failure and must not look
           the same.

Usage:
    python3 verify.py
    python3 verify.py --selftest
"""
import hashlib
import json
import os
import sys

HANDOFF = "handoff"
LOGS = "logs"

STEPS = [
    (1, "poem-writer", "01-poem.json", None),
    (2, "poem-translator", "02-translation.json", "01-poem.json"),
    (3, "gist-publisher", "03-published.json", "02-translation.json"),
]

REQUIRED = ("step", "skill", "produced_at", "input_file", "input_sha256", "payload", "not_done")

OK, BAD, WARN = "PASS", "FAIL", "WARN"


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_json(path):
    """Return (obj, error). Never raises."""
    if not os.path.exists(path):
        return None, "file does not exist"
    if os.path.getsize(path) == 0:
        return None, "file is empty"
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as exc:
        return None, "not parseable as JSON: %s" % exc


def claimed_result(root, n):
    """What the model said about step n, from the claude -p JSON output.

    --output-format json yields either a single result object or an array of
    messages ending in one, depending on which settings loaded. Handle both.
    """
    obj, err = load_json(os.path.join(root, LOGS, "step%d.json" % n))
    if err:
        return None
    if isinstance(obj, list):
        obj = next((m for m in reversed(obj)
                    if isinstance(m, dict) and m.get("type") == "result"), None)
    if not isinstance(obj, dict):
        return None
    text = obj.get("result")
    if not isinstance(text, str):
        return None
    return {"text": text, "is_error": bool(obj.get("is_error"))}


def check_step(root, n, skill, filename, prev_filename):
    """Return a list of (level, message) for one step."""
    out = []
    path = os.path.join(root, HANDOFF, filename)
    obj, err = load_json(path)

    if err:
        out.append((BAD, "step %d (%s): %s -- %s. STEP DID NOT RUN." % (n, skill, filename, err)))
        claim = claimed_result(root, n)
        if claim and not claim["is_error"]:
            out.append((BAD, "  ...and it claimed success: %r" % claim["text"][:120]))
        return out

    missing = [k for k in REQUIRED if k not in obj]
    if missing:
        out.append((BAD, "step %d (%s): missing keys %s" % (n, skill, ", ".join(missing))))
        return out

    if obj.get("skill") != skill:
        out.append((BAD, "step %d: file names skill %r, expected %r" % (n, obj.get("skill"), skill)))
    if obj.get("step") != n:
        out.append((BAD, "step %d: file says step %r" % (n, obj.get("step"))))

    if prev_filename is None:
        if obj.get("input_sha256") is not None:
            out.append((WARN, "step %d: head of chain but carries an input_sha256" % n))
    else:
        prev_path = os.path.join(root, HANDOFF, prev_filename)
        if not os.path.exists(prev_path):
            out.append((BAD, "step %d: input %s is gone; cannot verify the chain" % (n, prev_filename)))
        else:
            actual = sha256(prev_path)
            recorded = obj.get("input_sha256")
            if recorded is None:
                out.append((BAD, "step %d: no input_sha256 -- did not prove it read %s" % (n, prev_filename)))
            elif recorded.lower() != actual:
                out.append((BAD, "step %d: input_sha256 mismatch. recorded %s, actual %s -- "
                                 "step ran but did not read the real input."
                            % (n, str(recorded)[:16], actual[:16])))
            else:
                out.append((OK, "step %d (%s): produced %s, chained to %s" % (n, skill, filename, prev_filename)))
                return out

    if not out or all(lvl == WARN for lvl, _ in out):
        out.append((OK, "step %d (%s): produced %s" % (n, skill, filename)))

    nd = obj.get("not_done") or []
    if nd:
        out.append((WARN, "step %d reported not-done: %s" % (n, "; ".join(str(x) for x in nd))))
    return out


def hook_findings(root):
    """What the PreToolUse probes observed. Answers the two doc questions."""
    lines = []
    skill_log = os.path.join(root, LOGS, "skill-invocations.jsonl")
    all_log = os.path.join(root, LOGS, "all-tools.jsonl")

    def read_jsonl(p):
        recs = []
        if not os.path.exists(p):
            return recs
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
        return recs

    matched = read_jsonl(skill_log)
    every = read_jsonl(all_log)
    skill_calls_seen = [r for r in every if r.get("tool_name") == "Skill"]

    lines.append("  Skill tool calls seen by the catch-all matcher : %d" % len(skill_calls_seen))
    lines.append("  payloads captured by matcher \"Skill\"           : %d" % len(matched))

    if skill_calls_seen and not matched:
        lines.append("  => matcher \"Skill\" did NOT fire. Do not build on it.")
    elif matched:
        lines.append("  => matcher \"Skill\" fires.")
        names = []
        for rec in matched:
            ti = rec.get("tool_input") or {}
            if isinstance(ti, dict) and "skill" in ti:
                names.append(ti["skill"])
        if names:
            lines.append("  => skill name IS in the payload at tool_input.skill: %s" % ", ".join(names))
        else:
            keys = sorted({k for r in matched for k in r.keys()})
            lines.append("  => no tool_input.skill found. payload keys: %s" % ", ".join(keys))
    elif not every:
        lines.append("  => no hook output at all. Hooks did not load, or nothing ran yet.")
    return lines


def main(root="."):
    results = []
    for n, skill, filename, prev in STEPS:
        results.extend(check_step(root, n, skill, filename, prev))

    print("Artifact check -- did each step actually run?")
    print("-" * 62)
    for level, msg in results:
        print("  [%s] %s" % (level, msg))

    print()
    print("Hook probe -- PreToolUse matcher \"Skill\"")
    print("-" * 62)
    for line in hook_findings(root):
        print(line)

    failed = sum(1 for lvl, _ in results if lvl == BAD)
    print()
    print("%d failure(s)." % failed if failed else "Chain verified end to end.")
    return 1 if failed else 0


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, HANDOFF))
        os.makedirs(os.path.join(d, LOGS))

        def write(name, obj):
            p = os.path.join(d, HANDOFF, name)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(obj, fh)
            return p

        def base(n, skill, inp=None, sha=None):
            return {"step": n, "skill": skill, "produced_at": "2026-08-27T00:00:00Z",
                    "input_file": inp, "input_sha256": sha, "payload": {}, "not_done": []}

        # missing file -> FAIL, and says the step did not run
        r = check_step(d, 1, "poem-writer", "01-poem.json", None)
        assert any(lvl == BAD and "DID NOT RUN" in m for lvl, m in r), r

        p1 = write("01-poem.json", base(1, "poem-writer"))
        r = check_step(d, 1, "poem-writer", "01-poem.json", None)
        assert any(lvl == OK for lvl, _ in r), r

        # correct hash -> PASS
        write("02-translation.json", base(2, "poem-translator", "handoff/01-poem.json", sha256(p1)))
        r = check_step(d, 2, "poem-translator", "02-translation.json", "01-poem.json")
        assert any(lvl == OK for lvl, _ in r), r
        assert not any(lvl == BAD for lvl, _ in r), r

        # invented hash -> FAIL even though the file exists and is well-formed
        write("02-translation.json", base(2, "poem-translator", "handoff/01-poem.json", "0" * 64))
        r = check_step(d, 2, "poem-translator", "02-translation.json", "01-poem.json")
        assert any(lvl == BAD and "mismatch" in m for lvl, m in r), r

        # null hash -> FAIL: never proved it read the input
        write("02-translation.json", base(2, "poem-translator", "handoff/01-poem.json", None))
        r = check_step(d, 2, "poem-translator", "02-translation.json", "01-poem.json")
        assert any(lvl == BAD and "did not prove" in m for lvl, m in r), r

        # empty file -> FAIL
        open(os.path.join(d, HANDOFF, "03-published.json"), "w").close()
        r = check_step(d, 3, "gist-publisher", "03-published.json", "02-translation.json")
        assert any(lvl == BAD and "empty" in m for lvl, m in r), r

        # missing file + a success claim -> both the failure AND the false claim
        os.remove(os.path.join(d, HANDOFF, "03-published.json"))
        with open(os.path.join(d, LOGS, "step3.json"), "w", encoding="utf-8") as fh:
            json.dump({"result": "Published the gist successfully.", "is_error": False}, fh)
        r = check_step(d, 3, "gist-publisher", "03-published.json", "02-translation.json")
        assert any("claimed success" in m for _, m in r), r

    print("selftest ok")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--claim" in sys.argv:
        step_n = int(sys.argv[sys.argv.index("--claim") + 1])
        claim = claimed_result(".", step_n)
        print("<no parsable result>" if claim is None
              else claim["text"][:110].replace("\n", " "))
        sys.exit(0)
    sys.exit(main())
