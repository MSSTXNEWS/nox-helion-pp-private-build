#!/usr/bin/env bash
set -euo pipefail

R=/tmp/nox_build_inventory_20261122.txt
if [[ ! -s "$R" ]]; then
  echo "NO_REPORT $R"
  exit 2
fi
printf '%s\n' '-- S1 CURRENT TREE --'
grep '^TREE|' "$R" || true
printf '\n%s\n' '-- NEWEST BRAIN/CORE ARCHIVE GROUPS (name/hash/size) --'
awk '
/-- SMALL NOX\/BRAIN ARCHIVE SHA-256/ { p=1; next }
/-- KNOWN SOURCE TREE MANIFEST ROOTS/ { p=0 }
p { print }
' "$R" | grep -Ei 'NOX.*(BRAIN|CORE|UNIFIED|V[0-9])' | sort -t'|' -k4,4r | head -n 14 || true
printf '\n%s\n' '-- RECENT NOX BUILD DIRECTORIES --'
awk '
/-- BUILD DIRECTORIES/ { p=1; next }
/-- BUILD \/ MODEL/ { p=0 }
p { print }
' "$R" | grep -Ei 'NOX|BRAIN|CORE|v[0-9]' | sort -r | head -n 14 || true