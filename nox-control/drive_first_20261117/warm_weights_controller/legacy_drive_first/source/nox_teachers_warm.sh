#!/usr/bin/env bash
# nox_teachers_warm.sh (t145u)
# Idempotent, fail-closed warm-load of teacher/judge/vision/whisper GGUFs
# into /dev/shm/nox_t802u, then refresh /root/nox/models/{teachers,judge,...} symlinks.
# Usage: nox_teachers_warm.sh [--check]
#   --check  inspect only: no downloads, no deletes, no symlink changes.
set -euo pipefail

export TZ=Europe/Moscow
LOG=/var/log/nox/teachers_warm.log
MANIFEST="${TEACHERS_MANIFEST:-/root/nox/ops/teachers_manifest.json}"
SHM_ROOT=/dev/shm/nox_t802u
MODELS=/root/nox/models
RESERVE_BYTES=$((512 * 1024 * 1024))
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

mkdir -p "$(dirname "$LOG")" "$SHM_ROOT"
log() { printf '%s %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"; }
fail() { log "FAIL: $*"; exit 1; }

[[ -f "$MANIFEST" ]] || fail "manifest missing: $MANIFEST"
command -v python3 >/dev/null || fail "python3 required"
command -v curl >/dev/null || fail "curl required"
command -v sha256sum >/dev/null || fail "sha256sum required"
command -v stat >/dev/null || fail "stat required"

# dir|name|size|sha256|hf_url|drive_id
mapfile -t ITEMS < <(python3 - "$MANIFEST" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
files = m.get("files")
if not isinstance(files, list) or not files:
    sys.stderr.write("manifest has no files[]\n")
    sys.exit(2)
for f in files:
    def c(x):
        return str(x if x is not None else "").replace("|", " ").replace("\n", " ").strip()
    try:
        size = int(f.get("size", 0))
    except (TypeError, ValueError):
        size = 0
    print("|".join([
        c(f.get("dir", "")),
        c(f.get("name", "")),
        str(size),
        c(f.get("sha256", "")),
        c(f.get("hf_url", "")),
        c(f.get("drive_id", "")),
    ]))
PY
)

shm_avail() { df -B1 --output=avail /dev/shm | tail -1 | tr -d ' '; }

placeholder() {
  case "${1:-}" in
    ""|pending*|upload_*|none|null|UNKNOWN) return 0 ;;
    *) return 1 ;;
  esac
}

usable_url() {
  case "${1:-}" in
    http://*|https://*) return 0 ;;
    *) return 1 ;;
  esac
}

ensure_symlink() {
  local link="$1" target="$2"
  mkdir -p "$target"
  if [[ -L "$link" ]]; then
    local cur tgt
    cur=$(readlink -f "$link" 2>/dev/null || true)
    tgt=$(readlink -f "$target" 2>/dev/null || true)
    if [[ -n "$cur" && "$cur" == "$tgt" ]]; then
      log "SYMLINK_OK $link -> $target"
      return 0
    fi
    log "WARN: replacing symlink $link (was $(readlink "$link")) -> $target"
    rm -f "$link"
    ln -s "$target" "$link"
  elif [[ -e "$link" ]]; then
    fail "path exists and is not a symlink: $link"
  else
    mkdir -p "$(dirname "$link")"
    ln -s "$target" "$link"
    log "SYMLINK_NEW $link -> $target"
  fi
}

download_one() {
  local dest_part="$1" url="$2" expected_size="$3"
  mkdir -p "$(dirname "$dest_part")"
  log "DOWNLOAD start url=$url dest=$dest_part expected=$expected_size"
  if ! curl -fL --retry 20 --retry-delay 10 --retry-all-errors -C - \
      -o "$dest_part" "$url"; then
    log "CURL_FAIL url=$url"
    return 1
  fi
  local got
  got=$(stat -c %s "$dest_part" 2>/dev/null || echo 0)
  if [[ "$got" -ne "$expected_size" ]]; then
    log "SIZE_MISMATCH after download got=$got expected=$expected_size url=$url"
    return 1
  fi
  return 0
}

fetch_from_drive() {
  local dest_part="$1" drive_id="$2" expected_size="$3"
  log "DRIVE_FALLBACK id=$drive_id"
  if command -v rclone >/dev/null 2>&1; then
    if rclone listremotes 2>/dev/null | grep -qx 'noxdrive:'; then
      log "rclone copyid noxdrive $drive_id"
      if rclone backend copyid noxdrive "$drive_id" "$dest_part" >>"$LOG" 2>&1; then
        local got
        got=$(stat -c %s "$dest_part" 2>/dev/null || echo 0)
        if [[ "$got" -eq "$expected_size" ]]; then
          return 0
        fi
        log "DRIVE_RCLONE_SIZE_MISMATCH got=$got expected=$expected_size"
      else
        log "DRIVE_RCLONE_COPYID_FAILED id=$drive_id"
      fi
    else
      log "DRIVE_RCLONE_NOT_CONFIGURED (no noxdrive remote)"
    fi
  else
    log "DRIVE_RCLONE_ABSENT"
  fi
  # Last resort: public/uc URL. Usually fails for large private Drive files; fail-closed if so.
  if download_one "$dest_part" "https://drive.google.com/uc?export=download&confirm=t&id=${drive_id}" "$expected_size"; then
    return 0
  fi
  return 1
}

ok=0
skip=0
pending=0
failed=0

log "START check=$CHECK manifest=$MANIFEST shm_avail=$(shm_avail)"

for line in "${ITEMS[@]}"; do
  [[ -n "$line" ]] || continue
  IFS='|' read -r dir name size sha hf_url drive_id <<<"$line"
  [[ -n "$name" && "$size" -gt 0 ]] || fail "bad manifest row: $line"
  dest_dir="$SHM_ROOT/$dir"
  dest="$dest_dir/$name"
  part="$dest.part"
  mkdir -p "$dest_dir"

  if [[ -f "$dest" ]]; then
    got=$(stat -c %s "$dest")
    if [[ "$got" -eq "$size" ]]; then
      log "OK exists size_match $dir/$name size=$got"
      skip=$((skip + 1))
      ok=$((ok + 1))
      continue
    fi
    log "SIZE_WRONG $dir/$name got=$got expected=$size"
    if [[ "$CHECK" -eq 1 ]]; then
      log "CHECK would replace $dir/$name"
      failed=$((failed + 1))
      continue
    fi
    rm -f "$dest"
  else
    log "MISSING $dir/$name"
    if [[ "$CHECK" -eq 1 ]]; then
      log "CHECK would download $dir/$name"
      pending=$((pending + 1))
      continue
    fi
  fi

  avail=$(shm_avail)
  already=0
  [[ -f "$part" ]] && already=$(stat -c %s "$part")
  # Need remaining bytes plus reserve. If part is complete it will be sha-checked next.
  need=$((size - already + RESERVE_BYTES))
  if [[ "$need" -lt "$RESERVE_BYTES" ]]; then
    need=$RESERVE_BYTES
  fi
  if [[ "$avail" -lt "$need" ]]; then
    fail "NO_SPACE /dev/shm avail=$avail need=$need file=$dir/$name"
  fi
  log "SPACE ok avail=$avail need=$need file=$dir/$name"

  if placeholder "$sha"; then
    fail "SHA missing/placeholder for $dir/$name — refuse to download (fail-closed)"
  fi

  fetched=0
  if usable_url "$hf_url"; then
    if download_one "$part" "$hf_url" "$size"; then
      fetched=1
    else
      log "HF_DOWNLOAD_FAILED $dir/$name"
    fi
  else
    log "NO_HF_URL $dir/$name hf_url='$hf_url'"
  fi
  if [[ "$fetched" -ne 1 ]]; then
    if placeholder "$drive_id"; then
      fail "no usable source for $dir/$name (hf failed/missing, drive_id='$drive_id')"
    fi
    if fetch_from_drive "$part" "$drive_id" "$size"; then
      fetched=1
    else
      fail "could not fetch $dir/$name from HF or Drive"
    fi
  fi

  gotsha=$(sha256sum "$part" | awk '{print $1}')
  if [[ "$gotsha" != "$sha" ]]; then
    rm -f "$part"
    fail "SHA_MISMATCH $dir/$name got=$gotsha expected=$sha"
  fi
  log "SHA_OK $dir/$name $sha"
  mv -f "$part" "$dest"
  log "PUBLISHED $dir/$name"
  ok=$((ok + 1))
done

if [[ "$CHECK" -eq 1 ]]; then
  # Symlink inspection only — no changes.
  for pair in teachers:teachers judge:judge vision:vision whisper:whisper; do
    link="$MODELS/${pair%%:*}"
    target="$SHM_ROOT/${pair##*:}"
    if [[ -L "$link" ]]; then
      log "CHECK_SYMLINK $link -> $(readlink "$link")"
    elif [[ -e "$link" ]]; then
      log "CHECK_SYMLINK_NOT_LINK $link"
    else
      log "CHECK_SYMLINK_ABSENT $link (would create -> $target)"
    fi
  done
  log "CHECK_DONE ok=$ok skip=$skip pending=$pending failed=$failed shm_avail=$(shm_avail)"
  if [[ "$failed" -gt 0 || "$pending" -gt 0 ]]; then
    exit 1
  fi
  exit 0
fi

ensure_symlink "$MODELS/teachers" "$SHM_ROOT/teachers"
ensure_symlink "$MODELS/judge" "$SHM_ROOT/judge"
[[ -d "$SHM_ROOT/vision" ]] && ensure_symlink "$MODELS/vision" "$SHM_ROOT/vision"
[[ -d "$SHM_ROOT/whisper" ]] && ensure_symlink "$MODELS/whisper" "$SHM_ROOT/whisper"

log "DONE ok=$ok shm_avail=$(shm_avail)"
exit 0
