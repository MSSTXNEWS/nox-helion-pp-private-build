"""Reproducible exact-source patch; never executes the warm script."""
import difflib
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BEFORE_SHA='437739550dbdff28380a95302c1cc1e98ceab3f147de898b40dd8ec82ef80389'


def build():
    raw=(ROOT/'source/nox_teachers_warm.sh').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BEFORE_SHA:raise ValueError('SOURCE_SHA_CHANGED')
    original=raw.decode();text=original
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('PATCH_ANCHOR_NOT_UNIQUE:'+old[:60])
        text=text.replace(old,new,1)
    replace('# nox_teachers_warm.sh (t145u)','# nox_teachers_warm.sh (t145u; exact-source DRIVE_FIRST patch)')
    replace('command -v curl >/dev/null || fail "curl required"\n','')
    replace('# dir|name|size|sha256|hf_url|drive_id','# dir|name|size|sha256|drive_id|drive_verified; historical hf_url is ignored.')
    replace('    print("|".join([', '''    receipt = f.get("drive_verification", {})
    verified = (isinstance(receipt, dict) and receipt.get("verified") is True
        and receipt.get("drive_id") == f.get("drive_id")
        and receipt.get("size") == size and receipt.get("sha256") == f.get("sha256")
        and bool(receipt.get("receipt_id")) and bool(receipt.get("verified_at")))
    print("|".join([''')
    replace('        c(f.get("hf_url", "")),\n','')
    replace('        c(f.get("drive_id", "")),','        c(f.get("drive_id", "")),\n        "1" if verified else "0",')
    replace(')\n\nshm_avail()',')\n[[ "${#ITEMS[@]}" -gt 0 ]] || fail "HOLD: manifest has no readable rows"\n\nshm_avail()')
    start=text.index('usable_url() {');end=text.index('ensure_symlink() {',start)
    text=text[:start]+text[end:]
    replace('''    log "WARN: replacing symlink $link (was $(readlink "$link")) -> $target"
    rm -f "$link"
    ln -s "$target" "$link"''','''    fail "HOLD: existing symlink differs; preserving $link -> $(readlink "$link")"''')
    start=text.index('download_one() {');end=text.index('\nok=0',start)
    text=text[:start]+'''fetch_from_drive() {
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
''' +text[end:]
    replace("IFS='|' read -r dir name size sha hf_url drive_id", "IFS='|' read -r dir name size sha drive_id drive_verified")
    replace('''    log "SIZE_WRONG $dir/$name got=$got expected=$size"
    if [[ "$CHECK" -eq 1 ]]; then
      log "CHECK would replace $dir/$name"
      failed=$((failed + 1))
      continue
    fi
    rm -f "$dest"''','''    log "HOLD: existing size mismatch; preserved $dir/$name got=$got expected=$size"
    failed=$((failed + 1))
    continue''')
    replace('''  avail=$(shm_avail)''','''  if placeholder "$drive_id" || [[ ! "$drive_id" =~ ^[A-Za-z0-9_-]{10,200}$ || "$drive_verified" != 1 ]]; then
    fail "HOLD: verified whole-object Drive binding required for $dir/$name"
  fi
  [[ "$sha" =~ ^[a-f0-9]{64}$ ]] || fail "HOLD: pinned SHA256 required for $dir/$name"
  [[ ! -e "$dest" && ! -L "$dest" ]] || fail "HOLD: existing target preserved: $dest"

  avail=$(shm_avail)''')
    start=text.index('  fetched=0\n');end=text.index('\n  gotsha=',start)
    text=text[:start]+'''  if ! fetch_from_drive "$part" "$drive_id" "$size"; then
    fail "HOLD: Drive-only fetch unavailable for $dir/$name; no external fallback"
  fi
''' +text[end:]
    replace('''    rm -f "$part"
    fail "SHA_MISMATCH''','''    fail "HOLD: partial preserved; SHA_MISMATCH''')
    replace('''  mv -f "$part" "$dest"''','''  # Atomic no-clobber publication: never replace an existing weight path.
  ln -T -- "$part" "$dest" || fail "HOLD: target appeared; preserving both paths: $dest"
  rm -f "$part"''')
    replace('''ensure_symlink "$MODELS/teachers" "$SHM_ROOT/teachers"''','''[[ "$failed" -eq 0 ]] || fail "HOLD: existing-file conflicts preserved; no symlink changes"
ensure_symlink "$MODELS/teachers" "$SHM_ROOT/teachers"''')
    patched=text.encode();(ROOT/'nox_teachers_warm.drive_first.sh').write_bytes(patched)
    diff=''.join(difflib.unified_diff(original.splitlines(keepends=True),text.splitlines(keepends=True),
        fromfile='a/root/nox/ops/nox_teachers_warm.sh',tofile='b/root/nox/ops/nox_teachers_warm.sh'))
    (ROOT/'nox_teachers_warm.drive_first.patch').write_text(diff)
    return {'before_sha256':BEFORE_SHA,'after_sha256':hashlib.sha256(patched).hexdigest(),'source_bytes':len(raw),'patched_bytes':len(patched)}


if __name__=='__main__':
    import json
    print(json.dumps(build()))
