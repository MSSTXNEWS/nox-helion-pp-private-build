#!/usr/bin/env bash
set -euo pipefail

R=/tmp/nox_build_inventory_20261122.txt
if [[ ! -s "$R" ]]; then echo "NO_REPORT $R"; exit 2; fi

printf '%s\n' '-- EXISTING SOURCE MANIFEST ROOTS --'
grep '^TREE|' "$R" || true

printf '\n%s\n' '-- ARCHIVE CANDIDATES --'
awk '
/-- SMALL NOX\/BRAIN ARCHIVE SHA-256/ { p=1; next }
/-- KNOWN SOURCE TREE MANIFEST ROOTS/ { p=0 }
p { print }
' "$R" | grep -Ei 'brain|core|unified|v[0-9]|wow7' | tail -n 12 | cut -c1-190 || true

printf '\n%s\n' '-- RECENT BUILD PATHS --'
awk '
/-- BUILD DIRECTORIES/ { p=1; next }
/-- BUILD \/ MODEL/ { p=0 }
p { print }
' "$R" | grep -Ei '/root/nox/(src/wow7|v7_src_v6|state/v7|backups/v7|in_flash|v5)' | sort -r | head -n 12 | cut -c1-190 || true

printf '\n%s\n' '-- CANDIDATE ROOT METADATA --'
for d in /root/nox/src/wow7/brain /root/nox/v7_src_v6/nox_wow /root/nox/backups/v7/V7-04 /root/nox/state/v7 /root/nox/in_flash/NOX_S1_FLASH_OPTIM_EXEC_FULL_20261122; do
  [[ -d "$d" ]] || continue
  printf 'DIR|%s|' "$d"
  find "$d" -type f -printf '.' | wc -c | tr -d ' '
  printf '|'
  du -sb "$d" | cut -f1
  find "$d" -maxdepth 3 -type f \( -iname '*manifest*' -o -iname '*sha256*' -o -iname '*version*' -o -iname '*prompt*' -o -iname 'README*' \) -printf '%s|%p\n' | sort -nr | head -n 5
done
