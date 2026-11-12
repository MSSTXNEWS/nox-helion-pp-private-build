#!/usr/bin/env python3
"""Physical ZIP and static-route acceptance for NOX unified WEB.

Does not start local Windows services, models, or a fake backend.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urlsplit

ROUTES=("index.html","chat.html","memory.html","training.html","models.html",
        "system.html","settings.html","projects.html","cinema.html","install.html")
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.buttons=0
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        for key in ("src","href","poster"):
            if d.get(key):self.links.append((tag,key,d[key]))
        if tag=="button":self.buttons+=1
def digest(b):return hashlib.sha256(b).hexdigest()
def run(archive,original_web):
    with zipfile.ZipFile(archive) as z,zipfile.ZipFile(original_web) as original:
        corrupt=z.testzip()
        if corrupt:raise ValueError("ZIP_CRC_FAILED: "+corrupt)
        web={p:original.read(p) for p in original.namelist() if not p.endswith("/")}
        merged={p[5:]:z.read(p) for p in z.namelist() if p.startswith("site/") and not p.endswith("/")}
        qa={p:z.read(p) for p in z.namelist() if p.startswith("qa/") and not p.endswith("/")}
        if not set(ROUTES).issubset(merged):raise ValueError("MISSING_WEB_ROUTES")
        if merged["index.html"]!=web["index.html"]:raise ValueError("ORIGINAL_D02_CHANGED")
        preserved=[p for p in web if p not in ("chat.html","memory.html")]
        if any(merged[p]!=web[p] for p in preserved):raise ValueError("ORIGINAL_WEB_OTHER_CHANGED")
        if merged["original_web_v25_1/chat.html"]!=web["chat.html"]:raise ValueError("WEB_CHAT_BACKUP_CHANGED")
        if merged["original_web_v25_1/memory.html"]!=web["memory.html"]:raise ValueError("WEB_MEMORY_BACKUP_CHANGED")
        if not all(p in merged for p in ("pc/resonance.html","pc/memory.html","pc/vendor/fonts/tektur/tektur.css","pc/index.html")):
            raise ValueError("REAL_PC_CHAT_MISSING")
        if not all(p in merged["chat.html"] for p in (b"pc/resonance.html",)):
            raise ValueError("CHAT_NAVIGATION_NOT_WIRED")
        if not all(p in merged["memory.html"] for p in (b"pc/memory.html",)):
            raise ValueError("MEMORY_NAVIGATION_NOT_WIRED")
        if len(qa)<10:raise ValueError("ONEPASS_QA_MISSING")
        if re.search(rb"AIza[A-Za-z0-9_-]{30,}",merged.get("pc/pages/_vendor/excalidraw/excalidraw.production.min.js",b"")):
            raise ValueError("VENDOR_EXTERNAL_FIREBASE_KEY_NOT_REDACTED")
        html_routes={}
        missing=[]
        for page,body in merged.items():
            if not page.endswith(".html") or page.startswith("original_web_v25_1/") or page.endswith(".template.html"):
                continue
            v=Links();v.feed(body.decode("utf8","replace"));html_routes[page]={"buttons":v.buttons,"references":len(v.links)}
            for tag,key,ref in v.links:
                u=urlsplit(ref);path=u.path
                if not path or u.scheme or u.netloc or path.startswith(("#","data:","javascript:","/api/","/ws","/nox/")):
                    continue
                if path.startswith("/"): dest=PurePosixPath(path.lstrip("/")).as_posix()
                else:
                    stack=list(PurePosixPath(page).parent.parts)
                    if stack==["."]:stack=[]
                    for segment in PurePosixPath(path).parts:
                        if segment in ("","."):continue
                        if segment=="..":
                            if stack:stack.pop()
                        else:stack.append(segment)
                    dest="/".join(stack)
                if dest not in merged:
                    missing.append({"page":page,"target":ref,"tag":tag,"attr":key})
        if missing:raise ValueError("MISSING_STATIC_REFERENCES: "+json.dumps(missing[:12]))
        if html_routes.get("pc/resonance.html",{}).get("buttons",0)<10:
            raise ValueError("REAL_RESONANCE_CONTROLS_ABSENT")
        if html_routes.get("pc/memory.html",{}).get("buttons",0)<10:
            raise ValueError("REAL_MEMORY_CONTROLS_ABSENT")
        receipt=json.loads(z.read("NOX_PHYSICAL_MERGE_RECEIPT.json"))
        if receipt.get("release_accepted") is not False:
            raise ValueError("FAKE_RELEASE_ACCEPTANCE")
        result={"schema":"NOX-WEB-WOW-V25-PHYSICAL-STATIC-QA-v1",
                "status":"PASS_SOURCE_STATIC_WINDOWS_E2E_HOLD",
                "merged_zip_sha256":hashlib.sha256(open(archive,"rb").read()).hexdigest(),
                "web_unchanged_count":len(preserved),
                "web_route_count":len(ROUTES),
                "site_file_count":len(merged),
                "pc_chat_v25_files":receipt.get("pc_v25_full_static_files"),
                "pc_chat_v24_missing_added":receipt.get("pc_v24_fallback_files"),
                "qa_root_files":len(qa),
                "checked_user_html_pages":len(html_routes),
                "reference_404_count":0,
                "resonance_buttons":html_routes["pc/resonance.html"]["buttons"],
                "memory_buttons":html_routes["pc/memory.html"]["buttons"],
                "source_preservation":"PASS",
                "onepass_qa_present":True,
                "unverified":["Windows OneHost :8766","S03 readback","STOP","Ollama inference","GPU training","browser visual WOW30","WIN E07 same SHA"],
                "production_modified":False,"release_accepted":False}
        return result
def main():
    a=argparse.ArgumentParser();a.add_argument("--merged",required=True);a.add_argument("--original-web",required=True);a.add_argument("--report",required=True)
    n=a.parse_args()
    data=run(n.merged,n.original_web)
    with open(n.report,"w",encoding="utf8") as f:json.dump(data,f,ensure_ascii=False,indent=2)
    print(json.dumps(data,ensure_ascii=False))
if __name__=="__main__":
    try:main()
    except Exception as e:print("NOX_QA_HOLD "+str(e),file=sys.stderr);sys.exit(2)
