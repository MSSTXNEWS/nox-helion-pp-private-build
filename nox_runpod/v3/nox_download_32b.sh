#!/usr/bin/env bash
# DeepSeek-R1-Distill-Qwen-32B Q4_K_M. Download one official published GGUF into shared volume.
# NO remote deletion, NO replacement of verified model; verified SHA256 required.
set -Eeuo pipefail
ROOT=/workspace/nox/teachers/DeepSeek-R1-Distill-Qwen-32B
FILE=DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf
URL=https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf
EXPECTED=bed9b0f551f5b95bf9da5888a48f0f87c37ad6b72519c4cbd775f54ac0b9fc62
mkdir -p "$ROOT"
exec 9>"$ROOT/.download.lock"
flock -n 9 || { echo NOX_32B_DOWNLOAD_ALREADY_RUNNING; exit 0; }
if [ -s "$ROOT/$FILE" ] && printf '%s  %s\n' "$EXPECTED" "$ROOT/$FILE" | sha256sum --check --status; then
  echo "NOX_32B_ALREADY_VERIFIED $ROOT/$FILE"
else
  PART="$ROOT/$FILE.noxpart"
  # 20GB download plus 4GiB safety; cached complete models need no new space.
  FREE_KIB="$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')"
  PART_KIB=0
  if [ -f "$PART" ]; then PART_KIB="$(du -k "$PART" | awk '{print $1}')"; fi
  REQUIRED_KIB=$(( 24*1024*1024 - PART_KIB ))
  if [ "$REQUIRED_KIB" -lt $((4*1024*1024)) ]; then REQUIRED_KIB=$((4*1024*1024)); fi
  if [ "$FREE_KIB" -lt "$REQUIRED_KIB" ]; then
    echo "HOLD_32B_DISK_FREE_KIB=$FREE_KIB NEED_AT_LEAST_KIB=$REQUIRED_KIB"
    exit 2
  fi
  # Curl resumes a partial GGUF; incomplete or mismatched downloads are not promoted.
  curl --fail --location --continue-at - --retry 8 --retry-delay 5 --connect-timeout 30 \
    --speed-time 180 --speed-limit 10240 --output "$PART" "$URL"
  echo "NOX_32B_DOWNLOAD_SHA256_CHECK"
  if ! printf '%s  %s\n' "$EXPECTED" "$PART" | sha256sum --check --status; then
    echo "HOLD_32B_HASH_MISMATCH_PARTIAL_PRESERVED $PART"
    exit 3
  fi
  mv -n "$PART" "$ROOT/$FILE"
  if ! printf '%s  %s\n' "$EXPECTED" "$ROOT/$FILE" | sha256sum --check --status; then
    echo HOLD_32B_FINAL_SHA256
    exit 4
  fi
fi
python3 - "$ROOT" "$FILE" "$EXPECTED" <<'PY'
import datetime,json,os,pathlib,sys
root=pathlib.Path(sys.argv[1]); model=root/sys.argv[2]
proof={"teacher":"DeepSeek-R1-Distill-Qwen-32B","model_file":model.name,
       "sha256":sys.argv[3],"bytes":model.stat().st_size,
       "status":"SHA256_VERIFIED_SHARED","format":"GGUF_Q4_K_M",
       "model_source":"https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF",
       "verified_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
tmp=root/"nox_teacher_proof.json.tmp"
with tmp.open("w") as f:
 json.dump(proof,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
os.replace(tmp,root/"nox_teacher_proof.json")
print("NOX_32B_SHARED_SHA256_VERIFIED",str(model),model.stat().st_size,flush=True)
PY
