"""NOX PRIME exact-duplicate cleanup, preserves unique intelligence.

--execute removes only redundant Ollama aliases with the same 64-character
manifest digest, and older snapshots of the SAME official HF model that have
a complete SHA256 receipt. Never deletes unique Qwen model variants,
unique trained LoRA, S03, checkpoints, history, packages or NOX source.
No recursion outside the two explicit NOX-owned model namespaces.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from urllib.request import urlopen

ROOT=Path(r"C:\NOX_HELION\NOX_NEW")
PROTECTED={"qwen3:8b","qwen2.5-coder:7b","qwen3-embedding:0.6b",
           "nox:latest","nox-helion:latest"}
HEX64=re.compile(r"^(?:sha256:)?([a-fA-F0-9]{64})$")
NOX_MODELS=("Qwen3-0.6B","Qwen3-1.7B","Qwen3-4B",
            "Qwen2.5-Coder-1.5B-Instruct","Qwen3.5-2B")
SOURCE_EXT={".py",".ps1",".js",".ts",".tsx",".jsx",".json",".html",
            ".md",".txt",".yml",".yaml",".toml"}
MAX_SOURCE_FILES=8000
MAX_SOURCE_BYTES=100_000_000

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for piece in iter(lambda:f.read(4_194_304),b""):h.update(piece)
    return h.hexdigest()

def ollama_api(path):
    with urlopen("http://127.0.0.1:11434"+path,timeout=10) as r:
        obj=json.loads(r.read(3_000_000))
    if not isinstance(obj,dict):raise RuntimeError("OLLAMA_BAD_RESPONSE")
    return obj

def models(client=ollama_api):
    rows=client("/api/tags").get("models")
    if not isinstance(rows,list):raise RuntimeError("OLLAMA_TAGS_UNAVAILABLE")
    out={}
    for item in rows:
        if not isinstance(item,dict):continue
        name=item.get("name") or item.get("model")
        value=item.get("digest")
        match=HEX64.fullmatch(value) if isinstance(value,str) else None
        if not isinstance(name,str) or not match:continue
        if name in out and out[name]!=match[1].lower():
            raise RuntimeError("OLLAMA_TAG_COLLISION")
        out[name]=match[1].lower()
    return out

def loaded(client=ollama_api):
    rows=client("/api/ps").get("models")
    if not isinstance(rows,list):raise RuntimeError("OLLAMA_ACTIVE_MODELS_UNAVAILABLE")
    return {str(row.get("name") or row.get("model")) for row in rows
            if isinstance(row,dict)}

def source_references(root,names):
    repo=Path(root)/"brain"/"source"/"repo"
    if not (repo/".git").is_dir():
        raise RuntimeError("REPO_MISSING_FOR_REFERENCE_SCAN")
    hits=set()
    files=0
    bytes_read=0
    for folder,dirs,entries in os.walk(repo,followlinks=False):
        dirs[:]=[d for d in dirs if d not in
            (".git","node_modules",".venv","venv",".next","dist","build",
             "obj","bin","__pycache__") and not (Path(folder)/d).is_symlink()]
        for filename in entries:
            p=Path(folder)/filename
            if p.suffix.lower() not in SOURCE_EXT or p.is_symlink():continue
            try:
                size=p.stat().st_size
                if size>1_000_000:continue
                if files>=MAX_SOURCE_FILES or bytes_read+size>MAX_SOURCE_BYTES:
                    raise RuntimeError("SOURCE_SCAN_LIMIT_HOLD")
                data=p.read_text(encoding="utf-8",errors="replace").casefold()
            except OSError as exc:
                raise RuntimeError("SOURCE_SCAN_INCOMPLETE") from exc
            files+=1
            bytes_read+=size
            for name in names:
                if name.casefold() in data:hits.add(name)
    return hits

def aliases(catalog,active,refs):
    groups=defaultdict(list)
    for name,hash_value in catalog.items():
        groups[hash_value].append(name)
    proposed=[]
    for digest,group in sorted(groups.items()):
        if len(group)<2:continue
        names=sorted(group)
        locked=[x for x in names if (x in PROTECTED or x in active or
            x in refs or x.lower().startswith(("nox-","nox:","soul")))]
        keeper=locked[0] if locked else names[0]
        for name in names:
            if name!=keeper and name not in locked:
                proposed.append({"type":"OLLAMA_EXACT_ALIAS","delete":name,
                    "keep":keeper,"digest":digest,
                    "restore":["ollama","cp",keeper,name]})
    return proposed

def snapshot_receipt(path):
    if not path.is_dir() or path.is_symlink():return None
    manifest=path/"NOX_WEIGHTS_SHA256.json"
    if not manifest.is_file() or manifest.is_symlink():return None
    try:
        obj=json.loads(manifest.read_text(encoding="utf-8"))
        if obj.get("state")!="SHA256_CHECKED":return None
        digest=obj.get("sha256")
        if not isinstance(digest,dict) or not digest:return None
        if not isinstance(obj.get("revision"),str) or not re.fullmatch("[a-f0-9]{40}",obj["revision"]):
            return None
        if path.name!="revision_"+obj["revision"][:12]:return None
        for filename,expected in digest.items():
            if not isinstance(filename,str) or not re.fullmatch("[a-f0-9]{64}",str(expected)):
                return None
            relative=Path(filename)
            if relative.is_absolute() or ".." in relative.parts:return None
            item=path/relative
            if not item.is_file() or item.is_symlink() or sha256(item)!=expected:return None
        # No additional user-created data inside a downloaded model snapshot.
        permitted={str(Path(x)).replace("\\","/") for x in digest}
        permitted.add("NOX_WEIGHTS_SHA256.json")
        for found in path.rglob("*"):
            if found.is_symlink():return None
            if found.is_file():
                rel=found.relative_to(path).as_posix()
                if rel not in permitted and not rel.startswith(".cache/huggingface/"):
                    return None
        return {"revision":obj["revision"],"model_id":obj.get("model_id"),
                "byte_count":sum((path/f).stat().st_size for f in digest),
                "created_utc":str(obj.get("created_utc") or "")}
    except (OSError,TypeError,ValueError,KeyError,PermissionError):
        return None

def old_snapshots(root,process_commands):
    base=Path(root)/"brain"/"models"/"NOX_PRIME_V5"
    planned=[]
    for family in NOX_MODELS:
        folder=base/family
        if not folder.is_dir() or folder.is_symlink():continue
        candidates=[]
        for snapshot in folder.iterdir():
            receipt=snapshot_receipt(snapshot)
            if not receipt:continue
            expected_id="Qwen/"+family
            if receipt["model_id"]!=expected_id:continue
            candidates.append((snapshot,receipt))
        if len(candidates)<2:continue
        candidates.sort(key=lambda x:(x[1]["created_utc"],x[0].stat().st_mtime),
                        reverse=True)
        for snapshot,receipt in candidates[1:]:
            if any(str(snapshot).casefold() in cmd.casefold() for cmd in process_commands):
                continue
            planned.append({"type":"HF_OLD_VERIFIED_REVISION",
                            "path":str(snapshot),"family":family,
                            "revision":receipt["revision"],
                            "bytes":receipt["byte_count"],
                            "restore":"Official pinned HF model "+receipt["model_id"]+" revision "+receipt["revision"]})
    return planned

def process_commands():
    # Prevent deleting any model tree used by an active Python/GPU worker.
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("PSUTIL_REQUIRED_FOR_ACTIVE_MODEL_GUARD") from exc
    cmds=[]
    for proc in psutil.process_iter(attrs=["name","cmdline"]):
        try:
            if proc.info["name"] and proc.info["name"].lower().startswith(
                ("python","ollama","nox")):
                cmds.append(" ".join(proc.info.get("cmdline") or []))
        except (psutil.NoSuchProcess,psutil.AccessDenied):
            # Unknown active worker: fail closed.
            raise RuntimeError("PROCESS_INSPECTION_INCOMPLETE")
    return cmds

def obsolete_boot_copies(root,cmdlines):
    """Old byte-identical Git source exports, never active or modified files."""
    brain=Path(root).resolve()/"brain"
    base=brain/"skills"
    repo=brain/"source"/"repo"
    if not base.is_dir() or not (repo/".git").is_dir():return []
    found=defaultdict(list)
    for folder in base.iterdir():
        if not folder.is_dir() or folder.is_symlink():continue
        match=re.fullmatch(r"(PRIME_(?:LIVE|V8|STEP1))_([a-f0-9]{12})",folder.name)
        if not match:continue
        if any(str(folder).casefold() in command.casefold() for command in cmdlines):
            continue
        try:
            commit=subprocess.run(
                ["git","-C",str(repo),"rev-parse","--verify",match[2]+"^{commit}"],
                text=True,capture_output=True,check=True,timeout=15).stdout.strip()
            if not re.fullmatch(r"[a-f0-9]{40}",commit):continue
            files=list(folder.rglob("*"))
            if not files or len(files)>500:continue
            valid=True
            count=0
            for file in files:
                if file.is_symlink():
                    valid=False
                    break
                if not file.is_file():continue
                rel=file.relative_to(folder).as_posix()
                if not rel.startswith("coordination/soul_gpu_v1/"):
                    valid=False
                    break
                original=subprocess.run(
                    ["git","-C",str(repo),"rev-parse",commit+":"+rel],
                    capture_output=True,text=True,timeout=10)
                current=subprocess.run(
                    ["git","hash-object",str(file)],
                    capture_output=True,text=True,timeout=10)
                if (original.returncode!=0 or current.returncode!=0
                    or original.stdout.strip()!=current.stdout.strip()):
                    valid=False
                    break
                count+=1
            if not valid or count==0:continue
            found[match[1]].append((folder,commit,folder.stat().st_mtime))
        except (OSError,subprocess.SubprocessError,PermissionError):
            continue
    planned=[]
    # Keep one most recent, fully verified source copy for each purpose.
    for family,items in found.items():
        items.sort(key=lambda x:x[2],reverse=True)
        for folder,commit,_ in items[1:]:
            planned.append({"type":"GIT_VERIFIED_OBSOLETE_BOOT_COPY",
                            "path":str(folder),"git_commit":commit,
                            "kept":str(items[0][0]),
                            "restorable":True})
    return planned

def write_report(folder,data):
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/("cleanup_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+
                 "_"+uuid.uuid4().hex[:6]+".json")
    with path.open("x",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
        f.flush();os.fsync(f.fileno())
    return path

def cleanup(root,execute=False,client=ollama_api,run=None):
    root=Path(root).resolve()
    if not (root/"brain").is_dir():raise RuntimeError("NOX_BRAIN_MISSING")
    catalog=models(client)
    active=loaded(client)
    refs=source_references(root,list(catalog))
    alias_jobs=aliases(catalog,active,refs)
    commands=process_commands()
    snapshot_jobs=old_snapshots(root,commands)
    boot_jobs=obsolete_boot_copies(root,commands)
    report={"schema":"NOX_SAFE_EXACT_DUPLICATES_V1","mode":"EXECUTE" if execute else "PLAN",
            "at_utc":datetime.now(timezone.utc).isoformat(),
            "aliases":alias_jobs,"snapshots":snapshot_jobs,"obsolete_boot_copies":boot_jobs,
            "removed":[],"holds":[],"protected":{"loaded":sorted(active),
            "hardcoded":sorted(PROTECTED),"referenced":sorted(refs)},
            "not_touched":["S03","own trained LoRA","SOUL","unique model digests",
                           "native code","full GPU checkpoints","model teachers still unique"],
            "bytes_reclaimed_measured":0}
    report_path=write_report(root/"brain"/"telemetry"/"cleanup",report)
    free_before=shutil.disk_usage(root).free
    if execute:
        for job in alias_jobs:
            try:
                before=models(client)
                keep=job["keep"];delete=job["delete"];sha=job["digest"]
                if (before.get(keep)!=sha or before.get(delete)!=sha or
                    delete in loaded(client)):
                    raise RuntimeError("OLLAMA_STATE_CHANGED")
                command=["ollama","rm",delete]
                if run is None:
                    subprocess.run(command,check=True,timeout=90,capture_output=True,text=True)
                else:run(command)
                after=models(client)
                if delete in after or after.get(keep)!=sha:
                    raise RuntimeError("OLLAMA_DELETE_VERIFY_FAILED")
                report["removed"].append(job)
            except (OSError,RuntimeError,subprocess.SubprocessError) as ex:
                report["holds"].append({"item":job["delete"],"reason":type(ex).__name__})
        for job in snapshot_jobs:
            snapshot=Path(job["path"])
            try:
                if (not snapshot_receipt(snapshot) or
                    any(str(snapshot).casefold() in c.casefold() for c in process_commands())):
                    raise RuntimeError("SNAPSHOT_CHANGED_OR_LOADED")
                # Never clean an active current revision, even if timestamp order changed.
                if not any(p!=snapshot and snapshot_receipt(p) for p in snapshot.parent.iterdir()):
                    raise RuntimeError("NO_RETAINED_VERIFIED_REVISION")
                shutil.rmtree(snapshot)
                if snapshot.exists():raise RuntimeError("SNAPSHOT_REMOVAL_INCOMPLETE")
                report["removed"].append(job)
            except (OSError,PermissionError,RuntimeError) as ex:
                report["holds"].append({"item":job["path"],"reason":type(ex).__name__})
        for job in boot_jobs:
            try:
                current=obsolete_boot_copies(root,process_commands())
                if not any(row["path"]==job["path"] and
                           row["git_commit"]==job["git_commit"] for row in current):
                    raise RuntimeError("BOOT_COPY_CHANGED_OR_RUNNING")
                shutil.rmtree(job["path"])
                report["removed"].append(job)
            except (OSError,PermissionError,RuntimeError) as exc:
                report["holds"].append({"item":job["path"],
                                        "reason":type(exc).__name__})
    report["bytes_reclaimed_measured"]=max(0,shutil.disk_usage(root).free-free_before)
    final_path=write_report(root/"brain"/"telemetry"/"cleanup",report)
    return {"plan":str(report_path),"result":str(final_path),
            "candidate_aliases":len(alias_jobs),"candidate_old_snapshots":len(snapshot_jobs),
            "candidate_old_boot_copies":len(boot_jobs),
            "actually_removed":len(report["removed"]),
            "actual_reclaimed_bytes":report["bytes_reclaimed_measured"],
            "holds":report["holds"],"unique_trained_weights_removed":0}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    print(json.dumps(cleanup(args.root,args.execute),ensure_ascii=False,indent=2))
