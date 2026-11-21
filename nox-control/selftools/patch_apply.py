"""patch_apply: apply a unified diff (pure python). dry_run by default; .bak before write."""
import os
import re
import registry as R

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse(diff):
    files, cur, hunk = [], None, None
    lines = diff.splitlines()
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            old = l[4:].split("\t")[0].strip()
            new = lines[i + 1][4:].split("\t")[0].strip()
            cur = {"old": old, "new": new, "hunks": []}
            files.append(cur)
            hunk = None
            i += 2
            continue
        m = HUNK.match(l)
        if m and cur is not None:
            hunk = {"start": int(m.group(1)), "old": [], "new": []}
            cur["hunks"].append(hunk)
        elif hunk is not None and l[:1] in (" ", "-", "+"):
            if l[0] in " -":
                hunk["old"].append(l[1:])
            if l[0] in " +":
                hunk["new"].append(l[1:])
        elif hunk is not None and l == "":
            hunk["old"].append("")
            hunk["new"].append("")
        i += 1
    return files


def strip(p):
    return p[2:] if p[:2] in ("a/", "b/") else p


def apply_hunks(text, hunks):
    src = text.split("\n")
    trailing = text.endswith("\n")
    if trailing:
        src = src[:-1]
    if text == "":
        src = []
    shift = 0
    for h in hunks:
        old = h["old"]
        want = max(0, h["start"] - 1 + shift) if old else h["start"] + shift
        pos = None
        for d in sorted(range(-len(src) - 1, len(src) + 2), key=abs):
            c = want + d
            if c >= 0 and src[c:c + len(old)] == old and (old or c <= len(src)):
                pos = c
                break
        if pos is None:
            return None, "hunk @@ -%d does not match" % h["start"]
        src[pos:pos + len(old)] = h["new"]
        shift += len(h["new"]) - len(old)
    return "\n".join(src) + ("\n" if (trailing or text == "") and src else ""), None


@R.register("patch_apply", "write", {"properties": {
    "diff": {"type": "string"}, "root": {"type": "string", "default": "."}}, "required": ["diff"]},
    "Apply unified diff to files under root; dry_run default; backup .bak before write.")
def patch_apply(a):
    files = parse(a["diff"])
    if not files:
        return R.fail("no file sections in diff")
    root = R.safe_path(a["root"], must_exist=True)
    plan = []
    for f in files:
        creating = f["old"] == "/dev/null"
        deleting = f["new"] == "/dev/null"
        rel = strip(f["old"] if deleting else f["new"])
        path = R.safe_path(os.path.join(root, rel))
        if creating:
            if os.path.exists(path):
                return R.fail("file exists, cannot create: " + rel)
            text = ""
        else:
            if not os.path.isfile(path):
                return R.fail("missing file: " + rel)
            text = open(path, encoding="utf-8").read()
        new, err = apply_hunks(text, f["hunks"])
        if err:
            return R.fail("%s: %s" % (rel, err))
        plan.append((path, rel, new, deleting))
    if a["dry_run"]:
        return {"ok": True, "dry_run": True, "would_change": [p[1] for p in plan]}
    done = []
    for path, rel, new, deleting in plan:
        bak = R.backup_file(path)
        if deleting:
            os.remove(path)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
        done.append({"file": rel, "backup": bak})
    return {"ok": True, "dry_run": False, "changed": done}
