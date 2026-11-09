#!/usr/bin/env bash
# NOX donor acquisition queue: Qwen3.8-27B quantized teacher.
# Download only; never load another large model while primary NOX 9B is running.
set -Eeuo pipefail
ROOT=/workspace/nox
DEST="$ROOT/teachers/Qwen3.8-27B"
LOG="$ROOT/logs"
mkdir -p "$DEST" "$LOG"
exec 9>"$LOG/nox_teacher_27b_download.lock"
flock -n 9 || { echo "NOX_27B_DOWNLOAD_ALREADY_RUNNING"; exit 0; }
test "$(df -P /workspace | tail -n 1 | awk '{print $6}')" = "/workspace" || { echo "HOLD: persistent /workspace not mounted";exit 21; }
REPO='unsloth/Qwen3.8-27B-GGUF'
FILE='Qwen3.8-27B-UD-Q4_K_M.gguf'
# Need 17GB for model and substantial reserve for ongoing 9B checkpoints and final merges.
free=$(df -BG --output=avail /workspace | tail -n1 | tr -dc '0-9')
if [ -z "$free" ] || [ "$free" -lt 38 ]; then
  echo "HOLD_LOW_DISK_FREE_GIB=$free - preserve 9B checkpoints; no donor download"
  exit 22
fi
if [ -s "$DEST/$FILE" ] && [ "$(stat -c%s "$DEST/$FILE")" -gt 15000000000 ]; then
  echo "NOX_27B_TEACHER_ALREADY_PRESENT"
  exit 0
fi
PY="$ROOT/prime9b-venv/bin/python"
if [ ! -x "$PY" ]; then python3 -m venv --system-site-packages "$ROOT/prime9b-venv";fi
"$PY" -m pip install -q --disable-pip-version-check 'huggingface_hub>=0.35,<2'
# Download untrusted public model weights, only explicitly named GGUF.
"$PY" - "$REPO" "$FILE" "$DEST" <<'PY'
import hashlib,json,os,pathlib,sys,datetime
from huggingface_hub import hf_hub_download,model_info
repo,name,out=sys.argv[1:]
dest=pathlib.Path(out)
info=model_info(repo,files_metadata=True)
file=next((f for f in info.siblings if f.rfilename==name),None)
if not file:raise RuntimeError("Expected exact GGUF file missing from teacher repository")
if file.size and file.size > 25_000_000_000:raise RuntimeError("Teacher weights unexpectedly huge")
p=pathlib.Path(hf_hub_download(repo_id=repo,filename=name,local_dir=out))
h=hashlib.sha256()
with p.open("rb") as f:
 for chunk in iter(lambda:f.read(8*1024*1024),b""):h.update(chunk)
receipt={"repo":repo,"revision":info.sha,"filename":name,"bytes":p.stat().st_size,
         "sha256":h.hexdigest(),"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "purpose":"Future offline teacher inference and knowledge distillation",
         "status":"DOWNLOADED_NOT_LOADED_NOT_TRAINING"}
tmp=dest/"teacher_receipt.tmp.json"
tmp.write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding="utf-8")
os.replace(tmp,dest/"teacher_receipt.json")
print("NOX_27B_DONOR_DOWNLOADED",json.dumps(receipt),flush=True)
PY
echo "NOX_27B_READY_ON_PERSISTENT_DISK; current NOX 9B training unchanged"
