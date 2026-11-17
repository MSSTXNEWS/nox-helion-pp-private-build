#!/usr/bin/env bash
# nox_teachers_warm.sh (t145u; exact-source DRIVE_FIRST patch)
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
command -v sha256sum >/dev/null || fail "sha256sum required"
command -v stat >/dev/null || fail "stat required"

# dir|name|size|sha256|drive_id|drive_verified; historical hf_url is ignored.
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
    receipt = f.get("drive_verification", {})
    verified = (isinstance(receipt, dict) and receipt.get("verified") is True
        and receipt.get("drive_id") == f.get("drive_id")
        and receipt.get("size") == size and receipt.get("sha256") == f.get("sha256")
        and bool(receipt.get("receipt_id")) and bool(receipt.get("verified_at")))
    print("|".join([
        c(f.get("dir", "")),
        c(f.get("name", "")),
        str(size),
        c(f.get("sha256", "")),
        c(f.get("drive_id", "")),
        "1" if verified else "0",
    ]))
PY
)
[[ "${#ITEMS[@]}" -gt 0 ]] || fail "HOLD: manifest has no readable rows"

shm_avail() { df -B1 --output=avail /dev/shm | tail -1 | tr -d ' '; }

placeholder() {
  case "${1:-}" in
    ""|pending*|upload_*|none|null|UNKNOWN) return 0 ;;
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
    fail "HOLD: existing symlink differs; preserving $link -> $(readlink "$link")"
  elif [[ -e "$link" ]]; then
    fail "path exists and is not a symlink: $link"
  else
    mkdir -p "$(dirname "$link")"
    ln -s "$target" "$link"
    log "SYMLINK_NEW $link -> $target"
  fi
}

fetch_from_drive() {
  local dest_part="$1" drive_id="$2" expected_size="$3"
  # No HF, public-URL, or credential fallback. A configured Drive remote is required.
  if ! command -v rclone >/dev/null 2>&1; then
    log "HOLD: DRIVE_RCLONE_ABSENT"
    return 1
  fi
  if ! rclone listremotes 2>/dev/null | grep -qx 'noxdrive:'; then
    log "HOLD: DRIVE_RCLONE_NOT_CONFIGURED"
    return 1
  fi
  if [[ -e "$dest_part" || -L "$dest_part" ]]; then
    log "HOLD: existing partial preserved; provenance needs reconciliation: $dest_part"
    return 1
  fi
  log "DRIVE_ONLY id=$drive_id expected=$expected_size"
  if ! rclone backend copyid noxdrive: "$drive_id" "$dest_part" >>"$LOG" 2>&1; then
    log "HOLD: DRIVE_RCLONE_COPYID_FAILED id=$drive_id"
    return 1
  fi
  local got
  got=$(stat -c %s "$dest_part" 2>/dev/null || echo 0)
  [[ "$got" -eq "$expected_size" ]] || { log "HOLD: DRIVE_SIZE_MISMATCH got=$got expected=$expected_size"; return 1; }
  return 0
}

ok=0
skip=0
pending=0
failed=0

log "START check=$CHECK manifest=$MANIFEST shm_avail=$(shm_avail)"

for line in "${ITEMS[@]}"; do
  [[ -n "$line" ]] || continue
  IFS='|' read -r dir name size sha drive_id drive_verified <<<"$line"
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
    log "HOLD: existing size mismatch; preserved $dir/$name got=$got expected=$size"
    failed=$((failed + 1))
    continue
  else
    log "MISSING $dir/$name"
    if [[ "$CHECK" -eq 1 ]]; then
      log "CHECK would download $dir/$name"
      pending=$((pending + 1))
      continue
    fi
  fi

  if placeholder "$drive_id" || [[ ! "$drive_id" =~ ^[A-Za-z0-9_-]{10,200}$ || "$drive_verified" != 1 ]]; then
    fail "HOLD: verified whole-object Drive binding required for $dir/$name"
  fi
  [[ "$sha" =~ ^[a-f0-9]{64}$ ]] || fail "HOLD: pinned SHA256 required for $dir/$name"
  [[ ! -e "$dest" && ! -L "$dest" ]] || fail "HOLD: existing target preserved: $dest"

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

  if ! fetch_from_drive "$part" "$drive_id" "$size"; then
    fail "HOLD: Drive-only fetch unavailable for $dir/$name; no external fallback"
  fi

  gotsha=$(sha256sum "$part" | awk '{print $1}')
  if [[ "$gotsha" != "$sha" ]]; then
    fail "HOLD: partial preserved; SHA_MISMATCH $dir/$name got=$gotsha expected=$sha"
  fi
  log "SHA_OK $dir/$name $sha"
  # Atomic no-clobber publication: never replace an existing weight path.
  ln -T -- "$part" "$dest" || fail "HOLD: target appeared; preserving both paths: $dest"
  rm -f "$part"
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

[[ "$failed" -eq 0 ]] || fail "HOLD: existing-file conflicts preserved; no symlink changes"
ensure_symlink "$MODELS/teachers" "$SHM_ROOT/teachers"
ensure_symlink "$MODELS/judge" "$SHM_ROOT/judge"
[[ -d "$SHM_ROOT/vision" ]] && ensure_symlink "$MODELS/vision" "$SHM_ROOT/vision"
[[ -d "$SHM_ROOT/whisper" ]] && ensure_symlink "$MODELS/whisper" "$SHM_ROOT/whisper"

log "DONE ok=$ok shm_avail=$(shm_avail)"
exit 0
