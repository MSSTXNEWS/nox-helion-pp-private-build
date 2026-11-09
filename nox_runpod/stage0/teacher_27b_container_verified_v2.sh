#!/usr/bin/env bash
# Download verified Qwen3.5-27B teacher onto the 50GB container disk.
set -Eeuo pipefail
ROOT=/workspace/nox
DEST=/opt/nox_teacher_27b
mkdir -p "$DEST" "$ROOT/logs"
exec 9>"$ROOT/logs/nox_27b_container.lock"
flock -n 9 || { echo NOX_27B_DOWNLOAD_ALREADY_RUNNING; exit 0; }
if [ "$(stat -c %d /opt)" = "$(stat -c %d /workspace)" ]; then echo HOLD_DISKS_NOT_SEPARATE; exit 21; fi
if [ "$(df -B1 --output=avail /opt | tail -1 | tr -d ' ')" -lt 25000000000 ]; then echo HOLD_CONTAINER_DISK_LOW;exit 22;fi
PY="$ROOT/prime9b-venv/bin/python"
test -x "$PY" || { echo HOLD_PYTHON_ENV_MISSING;exit 23; }
"$PY" -m pip install -q 'huggingface_hub>=0.35,<2'
"$PY" - <<'PY'
from huggingface_hub import hf_hub_download,model_info
from pathlib import Path
import hashlib,json,datetime,os
repo="unsloth/Qwen3.5-27B-GGUF"
fn="Qwen3.5-27B-Q4_K_M.gguf"
dest=Path("/opt/nox_teacher_27b")
info=model_info(repo,files_metadata=True)
entry=next((s for s in info.siblings if s.rfilename==fn),None)
if entry is None: raise RuntimeError("Teacher file absent in Hub")
expected=(entry.lfs or {}).get("sha256") if isinstance(entry.lfs,dict) else getattr(entry.lfs,"sha256",None)
if not expected or len(expected)!=64:raise RuntimeError("Missing upstream LFS SHA256; refuse unverified model")
p=Path(hf_hub_download(repo_id=repo,filename=fn,revision=info.sha,local_dir=str(dest)))
h=hashlib.sha256()
with p.open("rb") as f:
 for x in iter(lambda:f.read(8*1024*1024),b""):h.update(x)
actual=h.hexdigest()
if actual.lower()!=expected.lower():raise RuntimeError("27B file checksum mismatch")
receipt={"repo":repo,"revision":info.sha,"filename":fn,"bytes":p.stat().st_size,
         "sha256":actual,"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "location":str(p),"state":"TEACHER_DOWNLOADED_VERIFIED_NOT_YET_DISTILLED"}
tmp=dest/"receipt.tmp.json"
tmp.write_text(json.dumps(receipt,indent=2),encoding="utf-8")
os.replace(tmp,dest/"teacher_receipt.json")
print("NOX_27B_VERIFIED_CONTAINER_DISK",p.stat().st_size,flush=True)
PY
