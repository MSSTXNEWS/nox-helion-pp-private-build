#!/usr/bin/env python3
"""Physical NOX WEB+PC CHAT V25 merger: one site, no runtime/production changes.

The local PC chat retains its original V25 web directory under /pc/, where
its relative vendor and script dependencies remain intact. Original WOW D02
and its assets remain the canonical root. Only navigation entrypoints change.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path
from merge_nox_web_wow import (ROUTES, chat_files, digest, digest_file,
                               extract_onepass_qa, read_archive, site_files)

TEXT_ASSETS = (".html", ".htm", ".js", ".mjs", ".css", ".json")
SENSITIVE = {
    "github_pat": re.compile(rb"github_pat_[A-Za-z0-9_]{24,}"),
    "ghp": re.compile(rb"ghp_[A-Za-z0-9]{28,}"),
    "api_key": re.compile(rb"sk-[A-Za-z0-9]{28,}"),
    "google_api": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
}
STATIC_ABS = re.compile(
    rb"""(?P<q>["'])(?:/)(?P<dir>vendor|v22|v23|v24|v25|predator|assets13|assets|nox-engines|nox-worlds|pages)/""",
    re.I,
)
STATIC_INTERNAL_PAGES = re.compile(rb"""(?P<q>["'])/(?P<page>menu|world|hub)\.html""", re.I)
REQUIRED_PC = ("chat.html", "resonance.html", "memory.html", "index.html")
NO_TOUCH_PATHS = ("C:\\NOX\\helion", "C:\\NOX\\lora", "C:\\NOX\\agents",
                  "127.0.0.1:8766", "Ollama", "S03", "OneHost")


def local_entry(label, target):
    """Accessible real navigation, not mock data or an empty UI."""
    title = "Резонанс" if label == "chat" else "Память S03"
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="refresh" content="0;url={target}">'
            f'<title>NOX HELION · {title}</title>'
            f'<script>location.replace({json.dumps(target,ensure_ascii=False)});</script>'
            f'</head><body><a href="{target}">{title} · открыть</a></body></html>\n').encode("utf-8")


def clean_static(name, data):
    if name == "pages/_vendor/excalidraw/excalidraw.production.min.js":
        # Vendored Excalidraw bundles a public Firebase room-persistence
        # API key. The NOX local canvas must not depend on remote Firebase.
        # Empty only this confirmed *vendor* key field, not other tokens.
        data = SENSITIVE["google_api"].sub(b"", data)
    if name.endswith(TEXT_ASSETS):
        for key, pattern in SENSITIVE.items():
            if pattern.search(data):
                raise ValueError("NOX_PC_SOURCE_POTENTIAL_SECRET_HOLD: " + key + " " + name)
        # Keep real API endpoints (/api/...) and external sites unchanged.
        if name.endswith((".html", ".htm", ".js", ".mjs", ".css")):
            data = STATIC_ABS.sub(lambda m: m.group("q") + b"/pc/" + m.group("dir") + b"/", data)
            return STATIC_INTERNAL_PAGES.sub(lambda m: m.group("q") + b"/pc/" + m.group("page") + b".html", data)
    return data


def merge_physical(web, pc25, pc24, qa):
    if not set(ROUTES).issubset(web):
        raise ValueError("NOX_WEB10_REQUIRED_ROUTES_MISSING")
    if not set(REQUIRED_PC).issubset(pc25):
        raise ValueError("NOX_PC_V25_RESONANCE_OR_MEMORY_SOURCE_MISSING")
    if not all(pc25.get(p) for p in REQUIRED_PC):
        raise ValueError("NOX_PC_V25_EMPTY_REQUIRED_SOURCE")
    site = dict(web)  # original WEB V25.1 untouched by default
    qa_files = dict(qa)
    unused_v24 = 0
    pc_added = 0
    pc_modified = 0
    collisions = []
    fallback = 0

    # Preserve both original HTML entrypoints and route to the LIVE V25 UI.
    for name in ("chat.html", "memory.html"):
        site["original_web_v25_1/" + name] = web[name]
    site["chat.html"] = local_entry("chat", "pc/resonance.html")
    site["memory.html"] = local_entry("memory", "pc/memory.html")
    site["resonance.html"] = local_entry("chat", "pc/resonance.html")

    for name, data in pc25.items():
        if name.startswith(("/", "../")):
            raise ValueError("NOX_PC_UNSAFE_PATH")
        file = "pc/" + name
        if file in site:
            raise ValueError("NOX_PC_NAMESPACE_COLLISION")
        normalized = clean_static(name, data)
        site[file] = normalized
        pc_added += 1
        if normalized != data:
            pc_modified += 1

    # V24 is a DONOR ONLY for *missing* resources; never replace V25.
    for name, data in pc24.items():
        if name in pc25:
            unused_v24 += 1
            continue
        if not name.endswith(TEXT_ASSETS) and "." not in Path(name).name:
            continue
        file = "pc/" + name
        if file not in site:
            site[file] = clean_static(name, data)
            fallback += 1

    # OneHost/PC backend code remains in its existing Windows process, not
    # imported into a new web backend. Original source archives remain on Drive.
    for name in web:
        if name in pc25 and digest(web[name]) != digest(pc25[name]):
            collisions.append(name)

    for name, value in qa_files.items():
        if not name or "/" in name or "\\" in name:
            raise ValueError("NOX_QA_PATH_HOLD: " + name)
    if site["index.html"] != web["index.html"]:
        raise ValueError("NOX_D02_CHANGED")

    case_keys = set()
    for name in site:
        folded = name.casefold()
        if folded in case_keys:
            raise ValueError("NOX_CASE_COLLISION_IN_MERGED_SITE: " + name)
        case_keys.add(folded)
    receipt = {
        "schema": "NOX-WEB-WOW-V25-PHYSICAL-SOURCE-STAGING-v1",
        "status": "SOURCE_MERGED_PHYSICAL_ONEHOST_QA_HOLD",
        "web_original_files": len(web),
        "pc_v25_full_static_files": pc_added,
        "pc_v25_static_rewritten": pc_modified,
        "pc_v24_fallback_files": fallback,
        "pc_v24_existing_untouched": unused_v24,
        "shared_source_divergences_resolved_by_namespace": sorted(collisions),
        "original_index_sha256": digest(web["index.html"]),
        "merged_index_sha256": digest(site["index.html"]),
        "original_web_chat_sha256": digest(web["chat.html"]),
        "original_web_memory_sha256": digest(web["memory.html"]),
        "source_sha256": {name:digest(content) for name,content in sorted(site.items())},
        "sources_count": len(site),
        "onepass_qa_files": len(qa_files),
        "chat_runtime": "EXISTING_PC_SERVER_127.0.0.1_8766_NOT_TESTED_HERE",
        "onehost_s03_stop": "NOT_TESTED_ON_WINDOWS",
        "gpu_training": "UNCHANGED_NOT_TESTED",
        "windows_exe": "NOT_BUILT",
        "production_modified": False,
        "no_duplicate_backend": True,
        "vendor_external_firebase_room_key_removed": True,
        "never_touch": list(NO_TOUCH_PATHS),
        "release_accepted": False
    }
    return site,qa_files,receipt


def output(out, site, qa, receipt, sources):
    if out.exists():
        raise ValueError("NOX_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    out.mkdir(parents=True)
    try:
        archive_path = out/"NOX_WEB_WOW_V25_PC_UNIFIED_SOURCE_CANDIDATE.zip"
        external_receipt = out/"NOX_PHYSICAL_MERGE_RECEIPT.json"
        receipt["sources"] = {key: {"sha256": digest_file(file),
                          "bytes": file.stat().st_size}
                          for key,file in sources.items()}
        with zipfile.ZipFile(archive_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,body in sorted(site.items()):
                z.writestr("site/"+name,body)
            for name,body in sorted(qa.items()):
                z.writestr("qa/onepass_v2_original/"+name,body)
            z.writestr("READ_ME_FIRST.txt",
                       "SOURCE STAGING ONLY. The V25 PC chat web lives at site/pc/.\n"
                       "Host /api must be backed by EXISTING running NOX on Windows.\n"
                       "D02 source is site/index.html; original chat/memory preserved.\n"
                       "Do NOT overwrite C:\\NOX or promote without E07 independent QA.\n")
            z.writestr("NOX_PHYSICAL_MERGE_RECEIPT.json",
                       json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
        with zipfile.ZipFile(archive_path) as z:
            if z.testzip() is not None:
                raise ValueError("NOX_OUTPUT_ZIP_CRC_FAILED")
            for name,payload in site.items():
                if digest(z.read("site/"+name))!=digest(payload):
                    raise ValueError("NOX_OUTPUT_FILE_HASH_FAIL: "+name)
        receipt["output_zip_sha256"] = digest_file(archive_path)
        receipt["output_zip_bytes"] = archive_path.stat().st_size
        external_receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",
                                   encoding="utf8")
        return archive_path
    except BaseException:
        shutil.rmtree(out,ignore_errors=True)
        raise


def main():
    ap=argparse.ArgumentParser()
    for key in ("web-v25","chat-v25","chat-v24","onepass-v2","output"):
        ap.add_argument("--"+key,required=True,type=Path)
    arg=ap.parse_args()
    files={"web":arg.web_v25,"pc_chat_v25":arg.chat_v25,
           "pc_chat_v24":arg.chat_v24,"onepass":arg.onepass_v2}
    web=site_files(read_archive(arg.web_v25),strict=True)
    pc25=chat_files(read_archive(arg.chat_v25))
    pc24=chat_files(read_archive(arg.chat_v24))
    qameta,qa=extract_onepass_qa(arg.onepass_v2,web)
    site,qa,r=merge_physical(web,pc25,pc24,qa)
    r["onepass_verification"]=qameta
    destination=output(arg.output,site,qa,r,files)
    print(json.dumps({"archive":str(destination),"status":r["status"],
                      "file_count":r["sources_count"],"zip_bytes":r["output_zip_bytes"],
                      "zip_sha256":r["output_zip_sha256"],
                      "v25_static_count":r["pc_v25_full_static_files"],
                      "v24_added":r["pc_v24_fallback_files"],
                      "shared_paths_namespaced":len(r["shared_source_divergences_resolved_by_namespace"])},
                     ensure_ascii=False))
    return 0


if __name__=="__main__":
    try:sys.exit(main())
    except (ValueError, zipfile.BadZipFile, OSError) as error:
        print("NOX_HOLD "+str(error),file=sys.stderr);sys.exit(2)
