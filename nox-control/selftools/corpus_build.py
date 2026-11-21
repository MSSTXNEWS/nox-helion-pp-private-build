"""corpus_build: acceptance cards (markdown tables) + git commits -> instruction jsonl, deduped."""
import glob
import hashlib
import json
import os
import re
import registry as R

ROW = re.compile(r"^\|\s*([A-Z]\d+)\s*\|(.+)\|\s*$")


def norm_key(*parts):
    return hashlib.sha1(re.sub(r"\s+", " ", " ".join(parts)).strip().lower().encode()).hexdigest()


def cards(paths):
    for fp in paths:
        for l in open(fp, encoding="utf-8", errors="replace"):
            m = ROW.match(l.rstrip())
            if not m:
                continue
            cells = [c.strip() for c in m.group(2).split("|")]
            if len(cells) >= 2 and cells[0] and cells[1] and not set(cells[0]) <= set("-: "):
                yield {"source": "card:%s#%s" % (os.path.basename(fp), m.group(1)), "instruction": cells[0], "output": cells[1]}


def commits(limit, cwd):
    r = R.run(["git", "log", "-n", str(limit), "--format=%H%x1f%s%x1f%b%x1e"], cwd=cwd)
    if r["rc"] != 0:
        return
    for rec in r["out"].split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) < 3 or not parts[1].strip():
            continue
        body = re.sub(r"^(Co-Authored-By|Claude-Session):.*$", "", parts[2], flags=re.M).strip()
        if len(body) >= 20:
            yield {"source": "commit:" + parts[0][:10], "instruction": parts[1].strip(), "output": body}


@R.register("corpus_build", "write", {"properties": {
    "cards_glob": {"type": "string", "default": "coordination/**/*.md"}, "commit_limit": {"type": "integer", "default": 200},
    "out": {"type": "string", "default": "/root/nox/state/corpus/corpus.jsonl"}, "include_commits": {"type": "boolean", "default": True}}},
    "Build instruction/output jsonl from acceptance-card table rows and commit messages; sha1 dedup; appends only new keys.")
def corpus_build(a):
    out = R.safe_path(a["out"])
    base = R.safe_path(".")
    files = sorted(glob.glob(os.path.join(base, a["cards_glob"]), recursive=True))
    seen = set()
    if os.path.exists(out):
        for l in open(out, encoding="utf-8"):
            try:
                seen.add(json.loads(l)["key"])
            except (ValueError, KeyError):
                pass
    new, dups = [], 0
    srcs = list(cards(files))
    if a["include_commits"]:
        srcs += list(commits(a["commit_limit"], base))
    for rec in srcs:
        k = norm_key(rec["instruction"], rec["output"])
        if k in seen:
            dups += 1
            continue
        seen.add(k)
        rec["key"] = k
        new.append(rec)
    res = {"ok": True, "new": len(new), "duplicates": dups, "card_files": len(files), "out": out, "dry_run": a["dry_run"]}
    if not a["dry_run"] and new:
        R.backup_file(out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return res
