#!/usr/bin/env python3
"""Exact-source WEB29 CSS rebase for slot 3A; source staging only, no OneHost writes.

Expected input: 3A+3D fail-closed candidate. Upstream CSS comes from the existing
3D GitHub file, not a second stylesheet or a newly drawn shell.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

BASE_SHA256 = "860584c4e69f19a6c73903bb73bacc930f384aaab6ed0acc98b9e2f85a002d27"
UPSTREAM_CSS_BLOB = "3a4514e05948cf2f886d9dcd27027ad67d154c35"
CSS_PATH = "site/nox-cinematic-accessibility-3d.css"
REQUIRED = ("site/index.html", "site/chat.html", "site/progress.html", "site/pc/menu.html", "site/pc/hub.html", "site/pc/resonance.html", "site/nox-orbit-14.js", "site/nox-engines/nox-world-shaders.mjs")

def digest(b):
    return hashlib.sha256(b).hexdigest()

def git_blob(b):
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()

def build(baseline, upstream_css, output):
    src, css, dst = Path(baseline), Path(upstream_css), Path(output)
    if digest(src.read_bytes()) != BASE_SHA256:
        raise ValueError("HOLD: baseline SHA mismatch, do not overwrite/rebase unknown source")
    new = css.read_bytes()
    if git_blob(new) != UPSTREAM_CSS_BLOB:
        raise ValueError("HOLD: upstream CSS Git blob mismatch")
    if src.resolve() == dst.resolve() or dst.exists():
        raise FileExistsError("HOLD: output overwrites an existing archive")
    with ZipFile(src) as original:
        names = original.namelist()
        if len(names) != 1214 or len(names) != len(set(names)) or not all(x in names for x in REQUIRED):
            raise ValueError("HOLD: original WEB29 member/path contract mismatch")
        if git_blob(original.read(CSS_PATH)) != "1e55b7ad84c4d05d91350d4c75f2f436c53895bc":
            raise ValueError("HOLD: preimage CSS blob changed")
        if b"nox-cinematic-accessibility-3d.css" not in original.read("site/chat.html"):
            raise ValueError("HOLD: chat stylesheet link missing")
        if b"progress.html" not in original.read("site/pc/menu.html"):
            raise ValueError("HOLD: Development menu missing")
        try:
            with ZipFile(dst, "w") as staged:
                for member in original.infolist():
                    staged.writestr(copy.copy(member), new if member.filename == CSS_PATH else original.read(member))
            with ZipFile(dst) as verified:
                if verified.namelist() != names or verified.testzip() is not None:
                    raise ValueError("HOLD: ZIP member order/CRC mismatch")
                changed = [n for n in names if original.read(n) != verified.read(n)]
                if changed != [CSS_PATH]:
                    raise ValueError("HOLD: changed forbidden original paths: " + repr(changed))
                return {"status":"SOURCE_TESTED","input_sha256":BASE_SHA256,"output_sha256":digest(dst.read_bytes()),"output_bytes":dst.stat().st_size,"member_count":len(names),"byte_identical_members":len(names)-len(changed),"changed":changed,"upstream_css_git_blob":git_blob(new),"zip_crc":"PASS","native_deployed":False}
        except Exception:
            dst.unlink(missing_ok=True)
            raise

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--base",required=True);p.add_argument("--css",required=True);p.add_argument("--out",required=True)
    a=p.parse_args()
    print(json.dumps(build(a.base,a.css,a.out),ensure_ascii=False,indent=2))
