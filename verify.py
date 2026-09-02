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

  ASKED    the run request in handoff/00-request.json is what came back: the
           theme reached step 1 and the target language reached step 2. A
           parameter the chain quietly ignored looks exactly like a successful
           run unless something compares the two ends.

  SERVED   (--check-gist, needs network) the gist actually serves back the exact
           bytes of handoff/poem.md. A recorded gist_url is a claim like any
           other; the only evidence that a publish happened is the remote
           content matching the local render byte for byte.

Usage:
    python3 verify.py
    python3 verify.py --check-gist
    python3 verify.py --selftest
"""
import hashlib
import json
import os
import subprocess
import sys

HANDOFF = "handoff"
LOGS = "logs"

REQUEST = "00-request.json"

STEPS = [
    (1, "poem-writer", "01-poem.json", REQUEST),
    (2, "poem-translator", "02-translation.json", "01-poem.json"),
    (3, "gist-publisher", "03-published.json", "02-translation.json"),
]

REQUIRED = ("step", "skill", "produced_at", "input_file", "input_sha256", "payload", "not_done")

OK, BAD, WARN = "PASS", "FAIL", "WARN"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256(path):
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


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
    else:  # every step is chained now, step 1 included -- to the run request
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


def request_evidence(request, poem, translation):
    """Pure: did --theme and --lang survive the trip? No IO.

    A chain that silently ignores a parameter looks identical to one that
    honoured it, unless what was asked for is compared with what came back.
    """
    out = []
    if request is None:
        return [(BAD, "no %s -- cannot tell what this run was asked for" % REQUEST)]

    asked_theme = request.get("theme")
    got_theme = (poem or {}).get("payload") or {}
    got_theme = got_theme.get("theme") if isinstance(got_theme, dict) else None
    if asked_theme is None:
        out.append((OK, "no theme was requested; step 1 chose its own subject"))
    elif got_theme is None:
        out.append((BAD, "theme %r was requested but step 1 recorded none" % asked_theme))
    elif got_theme != asked_theme:
        out.append((BAD, "theme requested %r, step 1 recorded %r -- not the same run"
                    % (asked_theme, got_theme)))
    else:
        out.append((OK, "theme %r reached step 1" % asked_theme))

    asked_lang = request.get("target_language")
    carried = (poem or {}).get("payload") or {}
    carried = carried.get("target_language") if isinstance(carried, dict) else None
    got_lang = (translation or {}).get("payload") or {}
    got_lang = got_lang.get("language") if isinstance(got_lang, dict) else None
    if not asked_lang:
        out.append((WARN, "%s names no target_language" % REQUEST))
    elif carried != asked_lang:
        out.append((BAD, "language %r requested, step 1 carried through %r -- step 2 "
                         "was handed the wrong target" % (asked_lang, carried)))
    elif got_lang != asked_lang:
        out.append((BAD, "language %r requested, step 2 produced %r"
                    % (asked_lang, got_lang)))
    else:
        out.append((OK, "language %r reached step 2 through step 1" % asked_lang))
    return out


def publish_evidence(published):
    """Pure: publishing is unconditional now, so published=false is a failure."""
    if published is None:
        return [(BAD, "no 03-published.json -- nothing was published")]
    payload = published.get("payload")
    if not isinstance(payload, dict):
        nd = "; ".join(str(x) for x in (published.get("not_done") or [])) or "no reason given"
        return [(BAD, "step 3 recorded no payload: %s" % nd)]
    if payload.get("published") is not True:
        nd = "; ".join(str(x) for x in (published.get("not_done") or [])) or "no reason given"
        return [(BAD, "step 3 did not publish, and publishing is not optional: %s" % nd)]
    return [(OK, "step 3 published to gist %s (locally claimed; --check-gist proves it)"
             % (payload.get("gist_id") or "<none recorded>"))]


GIST_FILE = "poem.md"


def gist_evidence(gist_obj, filename, local_bytes):
    """Pure: does the gist actually serve the bytes we rendered? No IO."""
    files = (gist_obj or {}).get("files") or {}
    entry = files.get(filename)
    if not isinstance(entry, dict):
        served = ", ".join(sorted(files)) or "nothing"
        return BAD, "gist has no file %r -- it serves %s" % (filename, served)
    if entry.get("truncated"):
        return WARN, "gist file %r came back truncated; cannot compare" % filename
    content = entry.get("content")
    if not isinstance(content, str):
        return BAD, "gist file %r carries no content" % filename
    remote = content.encode("utf-8")
    rsha, lsha = sha256_bytes(remote), sha256_bytes(local_bytes)
    if remote == local_bytes:
        return OK, "gist serves %s byte-identical to the local render (%s)" % (filename, rsha[:16])
    return BAD, ("gist %s differs from the local render: remote %s, local %s -- "
                 "the gist does not hold this run's output."
                 % (filename, rsha[:16], lsha[:16]))


def fetch_gist(gist_id):
    """Return (obj, error). Shells out to gh so auth stays gh's problem."""
    try:
        proc = subprocess.run(["gh", "api", "gists/%s" % gist_id],
                              capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return None, "gh is not installed"
    except subprocess.TimeoutExpired:
        return None, "gh api timed out"
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        hint = err[0] if err else "gh exited %d" % proc.returncode
        if "403" in hint:
            hint += "  (403 here usually means the wrong gh account is active, "\
                    "not a real rate limit -- see POC_GIST_ACCOUNT in run.sh)"
        return None, hint
    try:
        return json.loads(proc.stdout), None
    except Exception as exc:
        return None, "gh api returned unparseable JSON: %s" % exc


def check_gist(root="."):
    """Remote evidence for step 3. Network. Opt-in via --check-gist."""
    print("Remote check -- does the gist actually serve this run's poem?")
    print("-" * 62)
    obj, err = load_json(os.path.join(root, HANDOFF, "03-published.json"))
    if err:
        print("  [%s] no 03-published.json -- %s. Nothing was published." % (BAD, err))
        return 1
    payload = obj.get("payload") or {}
    if not payload.get("published"):
        nd = "; ".join(str(x) for x in (obj.get("not_done") or [])) or "no reason recorded"
        print("  [%s] step 3 recorded published=false (%s). Nothing to check." % (WARN, nd))
        return 0

    md_path = os.path.join(root, payload.get("markdown_path") or "handoff/poem.md")
    if not os.path.exists(md_path):
        print("  [%s] claims published but %s is gone; cannot compare." % (BAD, md_path))
        return 1
    local = open(md_path, "rb").read()

    recorded_md = payload.get("markdown_sha256")
    if recorded_md and recorded_md.lower() != sha256_bytes(local):
        print("  [%s] markdown_sha256 mismatch: recorded %s, actual %s -- step 3 "
              "did not hash the file it left behind."
              % (BAD, str(recorded_md)[:16], sha256_bytes(local)[:16]))

    gist_id = payload.get("gist_id")
    if not gist_id:
        print("  [%s] step 3 recorded no gist_id; nothing to check against." % BAD)
        return 1

    gist, err = fetch_gist(gist_id)
    if err:
        print("  [%s] could not read gist %s: %s" % (WARN, gist_id, err))
        return 0
    level, msg = gist_evidence(gist, payload.get("gist_file") or GIST_FILE, local)
    print("  [%s] %s" % (level, msg))

    actual_vis = "public" if gist.get("public") else "secret"
    claimed_vis = payload.get("visibility")
    if claimed_vis and claimed_vis != actual_vis:
        print("  [%s] visibility recorded %r, gist is actually %r."
              % (BAD, claimed_vis, actual_vis))
        level = BAD
    else:
        print("  [%s] gist is %s, and the artifact says so." % (OK, actual_vis))
    if actual_vis == "public":
        print("  [%s] this gist is PUBLIC. The poem is world-readable." % WARN)
    return 1 if level == BAD else 0


def main(root="."):
    results = []
    for n, skill, filename, prev in STEPS:
        results.extend(check_step(root, n, skill, filename, prev))

    print("Artifact check -- did each step actually run?")
    print("-" * 62)
    for level, msg in results:
        print("  [%s] %s" % (level, msg))

    request, _ = load_json(os.path.join(root, HANDOFF, REQUEST))
    poem, _ = load_json(os.path.join(root, HANDOFF, "01-poem.json"))
    translation, _ = load_json(os.path.join(root, HANDOFF, "02-translation.json"))
    published, _ = load_json(os.path.join(root, HANDOFF, "03-published.json"))

    asked = request_evidence(request, poem, translation) + publish_evidence(published)
    results.extend(asked)
    print()
    print("Request check -- did the run do what it was asked to?")
    print("-" * 62)
    for level, msg in asked:
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

    # request_evidence and publish_evidence are pure too.
    req = {"theme": "a lighthouse", "target_language": "Japanese"}
    p1 = {"payload": {"theme": "a lighthouse", "target_language": "Japanese"}}
    p2 = {"payload": {"language": "Japanese"}}
    assert not [1 for lvl, _ in request_evidence(req, p1, p2) if lvl == BAD]

    # theme silently swapped for one the model liked better
    bad1 = {"payload": {"theme": "the sea", "target_language": "Japanese"}}
    assert any(lvl == BAD and "not the same run" in m
               for lvl, m in request_evidence(req, bad1, p2))

    # step 1 dropped the language, so step 2 was handed nothing
    bad2 = {"payload": {"theme": "a lighthouse"}}
    assert any(lvl == BAD and "wrong target" in m
               for lvl, m in request_evidence(req, bad2, p2))

    # step 2 normalised "Japanese" to "ja" -- reads as the wrong language
    assert any(lvl == BAD and "step 2 produced" in m
               for lvl, m in request_evidence(req, p1, {"payload": {"language": "ja"}}))

    # no theme requested is a normal run, not a failure
    assert not [1 for lvl, _ in request_evidence(
        {"theme": None, "target_language": "Japanese"},
        {"payload": {"theme": None, "target_language": "Japanese"}}, p2) if lvl == BAD]
    assert any(lvl == BAD for lvl, _ in request_evidence(None, p1, p2))

    # publishing is unconditional: published=false is a failure, not a warning
    assert any(lvl == BAD for lvl, _ in publish_evidence(None))
    assert any(lvl == BAD for lvl, _ in publish_evidence(
        {"payload": {"published": False}, "not_done": ["gh blew up"]}))
    assert any(lvl == BAD for lvl, _ in publish_evidence({"payload": None, "not_done": []}))
    assert not [1 for lvl, _ in publish_evidence(
        {"payload": {"published": True, "gist_id": "abc"}}) if lvl == BAD]

    # gist_evidence is pure, so the remote check is testable without network.
    local = b"# T\n\nline\n"
    lvl, _ = gist_evidence({"files": {"poem.md": {"content": local.decode()}}}, "poem.md", local)
    assert lvl == OK, lvl
    lvl, m = gist_evidence({"files": {"poem.md": {"content": "# something else\n"}}}, "poem.md", local)
    assert lvl == BAD and "differs" in m, (lvl, m)
    lvl, m = gist_evidence({"files": {"other": {"content": "x"}}}, "poem.md", local)
    assert lvl == BAD and "no file" in m, (lvl, m)
    lvl, m = gist_evidence({"files": {"poem.md": {"truncated": True}}}, "poem.md", local)
    assert lvl == WARN, (lvl, m)
    lvl, m = gist_evidence({}, "poem.md", local)
    assert lvl == BAD, (lvl, m)
    # a non-ASCII poem must survive the utf-8 round trip, not just ASCII
    utf8 = "# O Peso das Horas\n\nchaleira\n".encode("utf-8")
    lvl, _ = gist_evidence({"files": {"poem.md": {"content": utf8.decode("utf-8")}}}, "poem.md", utf8)
    assert lvl == OK, lvl

    print("selftest ok")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--check-gist" in sys.argv:
        sys.exit(check_gist())
    if "--claim" in sys.argv:
        step_n = int(sys.argv[sys.argv.index("--claim") + 1])
        claim = claimed_result(".", step_n)
        print("<no parsable result>" if claim is None
              else claim["text"][:110].replace("\n", " "))
        sys.exit(0)
    sys.exit(main())
