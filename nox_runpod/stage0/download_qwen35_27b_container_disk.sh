#!/usr/bin/env bash
# Download 27B teacher onto EMPTY CONTAINER disk, not persistent /workspace.
set -Eeuo pipefail
TARGET=/opt/nox_teacher_27b
FILE=Qwen3.5-27B-Q4_K_M.gguf
URL='https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/resolve/main/Qwen3.5-27B-Q4_K_M.gguf'
HASH=84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806
mkdir -p "$TARGET" /workspace/nox/logs
exec 9>/workspace/nox/logs/nox_27b_container_download.lock
flock -n 9 || { echo NOX_27B_DOWNLOAD_ALREADY_RUNNING; exit 0; }
if [ "$(stat -c %d /opt)" = "$(stat -c %d /workspace)" ]; then echo HOLD_OPT_IS_NOT_SECOND_DISK;exit 20;fi
FREE=$(df -B1 --output=avail /opt | tail -1 | tr -d ' ')
if [ "$FREE" -lt 25000000000 ];then echo "HOLD_LOW_CONTAINER_DISK bytes_free=$FREE";exit 21;fi
if [ -s "$TARGET/$FILE" ];then
 actual="$(sha256sum "$TARGET/$FILE" | cut -d' ' -f1)"
 if [ "$actual" = "$HASH" ];then echo NOX_27B_ALREADY_VERIFIED;exit 0;fi
 echo HOLD_EXISTING_FILE_HASH_MISMATCH;exit 22
fi
echo NOX_27B_CONTAINER_DOWNLOAD_BEGIN
curl --fail --location --retry 8 --retry-delay 5 --connect-timeout 30 --continue-at - \
  --output "$TARGET/$FILE.part" "$URL"
actual="$(sha256sum "$TARGET/$FILE.part" | cut -d' ' -f1)"
if [ "$actual" != "$HASH" ];then echo "HOLD_SHA256_MISMATCH; actual=$actual";exit 23;fi
mv "$TARGET/$FILE.part" "$TARGET/$FILE"
python3 - <<'PY'
import datetime,json,os,pathlib
d=pathlib.Path("/opt/nox_teacher_27b")
s={"repo":"unsloth/Qwen3.5-27B-GGUF","filename":"Qwen3.5-27B-Q4_K_M.gguf","bytes":(d/"Qwen3.5-27B-Q4_K_M.gguf").stat().st_size,"sha256":"84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806","verified_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"location":"CONTAINER_DISK_NOT_PERSISTENT","state":"DOWNLOADED_NOT_LOADED_NOT_DISTILLED"}
(d/"teacher_receipt.json").write_text(json.dumps(s,ensure_ascii=False,indent=2))
print("NOX_27B_TEACHER_VERIFIED_ON_SECOND_DISK",s["bytes"],flush=True)
PY
echo "PRIMARY_NOX_UNTOUCHED GPU_NOT_STOPPED"
