"""NOX PACK01: verify actual original 729-file app and audit remaining 18 routes.

No source execution or extraction. Does not rewrite/merge/enable host features.
Report IDs and function names only; no original private source content.
"""
import ast
import hashlib
import io
import json
import pathlib
import re
import sys
import zipfile

EXPECTED_SHA="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
PARTS=("source_00.part","source_01.part","source_02.part")
BASE=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else pathlib.Path("original").resolve()
OUT=pathlib.Path(sys.argv[2]) if len(sys.argv)>2 else pathlib.Path("pack01-final18-original-audit.json")
TASKS={
 "chat.rag":(["rag","retriev","context","citation"],["helion","rag"]),
 "chat.voice":(["voice","mic","asr","talk"],["voice","helion"]),
 "models.licenses":(["license","model","rights"],["weights","model"]),
 "datasets.review":(["dataset","rights","manifest","train"],["train","weights"]),
 "training.start":(["train","start","lora","qlora"],["train","weights"]),
 "training.checkpoints":(["checkpoint","restore","resume"],["train","weights"]),
 "training.evaluate":(["evaluate","eval","loss"],["train","weights"]),
 "voice.settings":(["voice","tts","settings","speaker"],["voice","settings"]),
 "calls.history":(["calls","history","sip"],["call","voice"]),
 "media.player":(["player","video","media"],["media","video"]),
 "media.subtitles":(["subtitle","caption","srt"],["media","video"]),
 "browser.open":(["browser","navigate","webview"],["browser","web"]),
 "browser.bookmarks":(["bookmark","favorite","history"],["browser","web"]),
 "images.generate":(["image","comfy","diffus","generate"],["creative","image"]),
 "system.update":(["update","installer","upgrade"],["install","update"]),
 "system.backup":(["backup","restore","rollback"],["backup","system"]),
 "system.pc_control":(["pc_control","system","process","disk"],["pc","control"]),
 "mobile.connect":(["remote","mobile","tunnel","gateway"],["mobile","remote"])
}
if len(TASKS)!=18:raise AssertionError("Requires exactly 18 missing routes")
h=hashlib.sha256();parts={}
blob=io.BytesIO()
for part in PARTS:
    f=BASE/part
    if not f.is_file() or f.is_symlink():raise RuntimeError("SOURCE_PART_MISSING")
    count=0
    with f.open("rb") as stream:
        while buf:=stream.read(1048576):
            h.update(buf);blob.write(buf);count+=len(buf)
    parts[part]=count
if h.hexdigest()!=EXPECTED_SHA or sum(parts.values())!=60364346:
    raise RuntimeError("SOURCE_HASH_MISMATCH")
blob.seek(0)
matches={k:[] for k in TASKS}
files=0
with zipfile.ZipFile(blob) as arc:
    seen=set()
    for info in arc.infolist():
        p=info.filename
        if info.is_dir():continue
        files+=1
        if "\\" in p or p.startswith("/") or any(x in ("","..",".") for x in p.split("/")):
            raise RuntimeError("INVALID_SOURCE_PATH")
        if p.casefold() in seen:raise RuntimeError("CASE_COLLISION")
        seen.add(p.casefold())
        # Only inspect source metadata and small, textual files.
        if not p.endswith((".py",".cs",".ps1")) or info.file_size>524288:continue
        data=arc.read(info)
        try:text=data.decode("utf-8")
        except UnicodeDecodeError:continue
        functions=[]
        if p.endswith(".py"):
            try:tree=ast.parse(text,filename=p)
            except SyntaxError:continue
            for node in ast.walk(tree):
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    functions.append(node.name)
        elif p.endswith(".cs"):
            functions=re.findall(r'\b(?:public|internal)\s+(?:static\s+)?(?:async\s+)?[\w<>,\s\[\]?]+\s+(\w+)\s*\(',text)[:150]
        else:
            functions=re.findall(r'(?im)^\s*function\s+([a-zA-Z]\w*)',text)[:150]
        hay=(p+" "+" ".join(functions)).lower()
        for route,(tokens,paths) in TASKS.items():
            score=sum(2 if t in p.lower() else 1 for t in tokens if t in hay)
            if any(q in p.lower() for q in paths):score+=2
            if score<2:continue
            matching=[f for f in functions if any(t in f.lower() for t in tokens)]
            matches[route].append({"path":p,"file_sha256":hashlib.sha256(data).hexdigest(),
                                  "score":score,"methods":matching[:14],
                                  "methodCount":len(functions)})
if files!=729:raise RuntimeError("ORIGINAL_MEMBER_COUNT_DRIFT")
for key in matches:
    matches[key]=sorted(matches[key],key=lambda x:(-x["score"],x["path"]))[:12]
result={"schema":"NOX_PACK01_FINAL18_ORIGINAL_ROUTE_AUDIT_V1",
 "sourceSha256":EXPECTED_SHA,"originalFiles":files,"parts":parts,
 "status":"READ_ONLY_SOURCE_PROVENANCE_NOT_NATIVE_INTEGRATION",
 "routes":{key:{"candidates":matches[key],"provenMethods":[x for x in matches[key] if x["methods"]],
                 "hostBound":False,"exeAccepted":False} for key in TASKS}}
OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("NOX_FINAL18_AUDIT_PASS original_files=",files,"sha256=",EXPECTED_SHA,sep="")
for route in TASKS:
    items=matches[route]
    print("ROUTE",route,"candidates",len(items),"withMethods",sum(bool(x["methods"]) for x in items),
          "TOP",",".join(x["path"] for x in items[:3]))
print("SOURCE_ROUTE_MATCH_IS_NOT_RUNTIME_BINDING_OR_ACCEPTANCE")
