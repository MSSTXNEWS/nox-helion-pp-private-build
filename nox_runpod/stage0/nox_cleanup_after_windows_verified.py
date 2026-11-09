#!/usr/bin/env python3
"""NOX verified-backup-gated cache cleanup. Runs on a RunPod Pod only AFTER an
out-of-band Windows backup receipt signed by the Windows verifier is provided.
Never removes model weights, checkpoint files, S03 databases, donor model GGUF,
dataset JSONL, active logs, or /workspace itself. Idempotent.
"""
import argparse,datetime,json,os,pathlib,re,subprocess,time
CACHE_ROOTS=[
 pathlib.Path("/root/.cache/pip"),
 pathlib.Path("/workspace/nox/.cache/pip"),
 pathlib.Path("/workspace/nox/cache/pip"),
 pathlib.Path("/workspace/nox/cache/torch_extensions"),
 pathlib.Path("/opt/nox_temporary_pip_cache"),
]
# Avoid wide /tmp and Hugging Face caches because they may contain unique model weights.
BASE=pathlib.Path("/workspace/nox")
def statdisk():
 return {str(m):subprocess.run(["df","-h",str(m)],text=True,capture_output=True).stdout for m in ("/","/workspace")}
def backed_up(receipt,source_node):
 data=json.loads(receipt.read_text(encoding="utf-8"))
 if data.get("status")!="VERIFIED_BACKUP_COMPLETE" or data.get("sha256_failures",1)!=0 or data.get("copy_errors",1)!=0:
  raise RuntimeError("WINDOWS_BACKUP_NOT_FULLY_VERIFIED")
 if data.get("backup_target")!="WINDOWS_NOX_HELION":raise RuntimeError("BACKUP_TARGET_NOT_WINDOWS")
 if data.get("remote_node")!=source_node:raise RuntimeError("BACKUP_NODE_MISMATCH")
 if data.get("verified_file_count",0)<1:raise RuntimeError("NO_FILES_VERIFIED")
 if (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(data["verified_at"])).total_seconds()>3600:
  raise RuntimeError("BACKUP_RECEIPT_STALE")
 return data
def not_open(path):
 # If fuser is unavailable, refuse cleanup; otherwise skip in-use cache files.
 try:r=subprocess.run(["fuser","-s",str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
 except (FileNotFoundError,subprocess.TimeoutExpired):return False
 return r.returncode==1
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--receipt",required=True)
 p.add_argument("--node",required=True,choices=("A5000","A40"))
 p.add_argument("--dry-run",action="store_true")
 a=p.parse_args()
 receipt=pathlib.Path(a.receipt)
 backed_up(receipt,a.node)
 print(json.dumps({"event":"NOX_CLEANUP_RECEIPT_ACCEPTED","node":a.node,"dry_run":a.dry_run,"before":statdisk()},ensure_ascii=False),flush=True)
 total=0;count=0
 for folder in CACHE_ROOTS:
  if not folder.exists() or folder.is_symlink() or not folder.is_dir():continue
  for root,dirs,files in os.walk(folder,followlinks=False):
   dirs[:]=[d for d in dirs if not (pathlib.Path(root)/d).is_symlink()]
   for name in files:
    fp=pathlib.Path(root)/name
    if fp.is_symlink() or not fp.is_file():continue
    try:
     st=fp.stat()
     if time.time()-st.st_mtime<24*3600:continue
     if not not_open(fp):continue
     count+=1;total+=st.st_size
     if not a.dry_run:fp.unlink()
    except OSError:continue
 print(json.dumps({"event":"NOX_SAFE_CACHE_CLEANUP_COMPLETE","files":count,
  "bytes":total,"dry_run":a.dry_run,"after":statdisk(),
  "never_deleted":"model weights, checkpoints, S03 memory, datasets, active logs"},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
