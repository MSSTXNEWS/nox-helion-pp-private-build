#!/usr/bin/env python3
"""NOX WEB WOW source merger (staging-only, fail-closed, no live writes).

Merge order:
  WEB V25.1 original -> V24 missing chat resources -> V25 chat+memory and
  matching dependencies. Preserve WEB original D02/index/14 worlds.
The resulting candidate MUST pass physical OneHost/WebView2 QA before promotion.
"""
import argparse, hashlib, json, re, shutil, sys, zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

ROUTES = ("index.html", "chat.html", "memory.html", "training.html",
          "models.html", "system.html", "settings.html", "projects.html",
          "cinema.html", "install.html")
NO_OVERWRITE = {"index.html", "nox-home.mjs", "nox-orbit-original.js",
                "nox-orbit-14.css", "nox-engines/physical-worlds-v7.mjs"}
CHAT_MAIN = {"chat.html", "memory.html"}
MAX_FILES = 20000
MAX_UNCOMPRESSED = 3 * 1024**3

def digest(b):
    return hashlib.sha256(b).hexdigest()

def read_archive(p):
    if not p.is_file():
        raise ValueError("NOX_ARCHIVE_MISSING: "+str(p))
    files = {}
    total = 0
    with zipfile.ZipFile(p) as z:
        for info in z.infolist():
            if info.is_dir(): continue
            if info.flag_bits & 0x1: raise ValueError("NOX_ENCRYPTED_ZIP_HOLD")
            name = info.filename.replace("\\", "/")
            pos = PurePosixPath(name)
            if (not name or name.startswith("/") or ".." in pos.parts
                or ":" in name or "\x00" in name or len(pos.parts)>25
                or info.file_size>MAX_UNCOMPRESSED):
                raise ValueError("NOX_UNSAFE_ARCHIVE_ENTRY: "+name)
            if info.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError("NOX_SYMLINK_ENTRY_HOLD: "+name)
            total += info.file_size
            if total > MAX_UNCOMPRESSED or len(files) >= MAX_FILES:
                raise ValueError("NOX_ARCHIVE_SIZE_LIMIT")
            value=z.read(info)
            if name in files and files[name] != value:
                raise ValueError("NOX_DUPLICATE_ZIP_NAME_CONFLICT: "+name)
            files[name]=value
    return files

def site_files(raw, *, required=("index.html",), strict=True):
    # Locate the site root without presuming a ZIP-internal folder name.
    candidates = set()
    for path in raw:
        if path.endswith("/index.html") or path=="index.html":
            candidates.add(path[:-len("index.html")])
    for prefix in sorted(candidates, key=lambda p:(-sum((p+x) in raw for x in ROUTES),len(p))):
        if not all(prefix+x in raw for x in required):
            continue
        files={name[len(prefix):]:data for name,data in raw.items()
               if name.startswith(prefix) and len(name)>len(prefix)}
        if strict and any(not x in files for x in ROUTES):
            continue
        return files
    if strict:
        raise ValueError("NOX_WEB_SITE_ROOT_OR_REQUIRED_PAGES_MISSING")
    raise ValueError("NOX_CHAT_SITE_ROOT_MISSING")

def chat_files(raw):
    # More recent archive may be a Windows project tree rather than a site export.
    prefixes=[]
    for file in raw:
        for route in ("chat.html","memory.html"):
            if file.endswith(route):
                prefixes.append(file[:-len(route)])
    if not prefixes:
        raise ValueError("NOX_CHAT_AND_MEMORY_PAGES_MISSING")
    prefixes=sorted(set(prefixes),key=lambda p:(-sum((p+x) in raw for x in CHAT_MAIN),len(p)))
    root=prefixes[0]
    return {name[len(root):]:data for name,data in raw.items()
            if name.startswith(root) and len(name)>len(root)}

def dependencies(file, data):
    if not file.lower().endswith((".html",".css",".js",".mjs")): return set()
    text=data.decode("utf-8","replace")
    candidates=set()
    # Local script/style/resource references, including ES modules and CSS imports.
    for ref in re.findall(r'(?:src|href|from|url\s*\()\s*=?\s*["\x27]([^"\x27)]+)',text,re.I):
        ref=ref.split("?")[0].split("#")[0].strip()
        if not ref or ref.startswith(("#","/","//","http:","https:","data:","blob:")): continue
        pos=PurePosixPath(file).parent.joinpath(ref)
        parts=[]
        for s in pos.parts:
            if s in ("","."):continue
            if s=="..":
                if not parts:break
                parts.pop()
            else:parts.append(s)
        else:candidates.add("/".join(parts))
    return candidates

def choose_chat_sources(chat25, chat24):
    # V24 can supply only missing files, never override V25 content.
    combined=dict(chat24)
    combined.update(chat25)
    closure=set()
    queue=[p for p in CHAT_MAIN if p in chat25 or p in chat24]
    while queue:
        p=queue.pop()
        if p in closure or p not in combined:continue
        closure.add(p)
        for dep in dependencies(p,combined[p]):
            if dep not in closure and dep in combined:queue.append(dep)
    return combined, closure

def merge(web,chat25,chat24):
    merged=dict(web)
    combined,selected=choose_chat_sources(chat25,chat24)
    if not CHAT_MAIN.issubset(selected):
        raise ValueError("NOX_V25_CHAT_MEMORY_ENTRYPOINTS_MISSING")
    actions=[]; conflicts=[]
    for name in sorted(selected):
        body=combined[name]
        if name in NO_OVERWRITE:
            if name in web and web[name]!=body:
                conflicts.append({"path":name,"reason":"ORIGINAL_D02_PRESERVED"})
            continue
        old=merged.get(name)
        if old==body:
            actions.append({"path":name,"action":"IDENTICAL_REUSED"});continue
        if name in CHAT_MAIN:
            merged[name]=body
            actions.append({"path":name,"action":"V25_CHAT_ROUTE_REPLACED" if old else "CHAT_ROUTE_ADDED"})
        elif old is None:
            merged[name]=body;actions.append({"path":name,"action":"CHAT_DEPENDENCY_ADDED"})
        else:
            conflicts.append({"path":name,"reason":"SHARED_DEPENDENCY_DIFFERENT_SHA",
                              "web_sha256":digest(old),"chat_sha256":digest(body)})
    for path in ROUTES:
        if path not in merged:raise ValueError("NOX_REQUIRED_ROUTE_MISSING: "+path)
    if conflicts:
        return None,{"status":"HOLD_CONFLICTS","actions":actions,"conflicts":conflicts}
    # The output reports source integration, NEVER live backend acceptance.
    return merged,{"status":"SOURCE_MERGED_PHYSICAL_QA_HOLD","actions":actions,
                   "conflicts":[],"onehost":"NOT_TESTED","s03":"NOT_TESTED",
                   "gpu_training":"UNTOUCHED","production_modified":False}

def output_candidate(dest,merged,receipt,inputs):
    if dest.exists():raise ValueError("NOX_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    dest.mkdir(parents=True)
    try:
        if merged:
            for name,body in merged.items():
                p=dest/"site"/name
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(body)
            receipt["files_count"]=len(merged)
            receipt["file_sha256"]={p:digest(v) for p,v in sorted(merged.items())}
        receipt["inputs"]={name:{"path":str(path),"sha256":digest(path.read_bytes())}
                           for name,path in inputs.items()}
        (dest/"NOX_MERGE_RECEIPT.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (dest/"READ_ME.txt").write_text(
            "NOX WEB WOW: staging only. Never copy over a running C:\\NOX site.\n"
            "HOLD_CONFLICTS: resolve shared dependency conflicts before deployment.\n"
            "SOURCE_MERGED_PHYSICAL_QA_HOLD: requires OneHost, S03, STOP, GPU, 14 worlds and Windows acceptance.\n",
            encoding="utf-8")
        if merged:
            with zipfile.ZipFile(dest/"NOX_WEB_WOW_V25_UNIFIED_CANDIDATE.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
                for path in sorted((dest/"site").rglob("*")):
                    if path.is_file():
                        archive.write(path,arcname="site/"+path.relative_to(dest/"site").as_posix())
                archive.write(dest/"NOX_MERGE_RECEIPT.json",arcname="NOX_MERGE_RECEIPT.json")
                archive.write(dest/"READ_ME.txt",arcname="READ_ME.txt")
            with zipfile.ZipFile(dest/"NOX_WEB_WOW_V25_UNIFIED_CANDIDATE.zip") as verify:
                if verify.testzip() is not None:
                    raise ValueError("NOX_MERGED_ZIP_CRC_FAILED")
    except BaseException:
        shutil.rmtree(dest,ignore_errors=True)
        raise

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--web-v25",type=Path,required=True)
    a.add_argument("--chat-v25",type=Path,required=True)
    a.add_argument("--chat-v24",type=Path,required=True)
    a.add_argument("--output",type=Path,required=True)
    ns=a.parse_args()
    inputs={"web_v25":ns.web_v25,"chat_v25":ns.chat_v25,"chat_v24":ns.chat_v24}
    if ns.output.exists():
        raise SystemExit("NOX_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    web=site_files(read_archive(ns.web_v25),strict=True)
    chat25=chat_files(read_archive(ns.chat_v25))
    chat24=chat_files(read_archive(ns.chat_v24))
    merged,receipt=merge(web,chat25,chat24)
    receipt["policy"]="NO_LOSS; NO_NEW_BACKEND; V25_CHAT_CANONICAL; ORIGINAL_D02_PRESERVED"
    output_candidate(ns.output,merged,receipt,inputs)
    print(json.dumps({"status":receipt["status"],"conflicts":len(receipt["conflicts"]),
                      "staging":str(ns.output)},ensure_ascii=False))
    return 0 if merged else 2
if __name__=="__main__":
    try:sys.exit(main())
    except (ValueError,zipfile.BadZipFile) as e:
        print("NOX_MERGE_HOLD: "+str(e),file=sys.stderr);sys.exit(2)
