#!/usr/bin/env bash
set -euo pipefail

R=/tmp/nox_build_inventory_20261122.txt
if [[ ! -s "$R" ]]; then
  echo "NO_REPORT $R"
  exit 2
fi
printf 'REPORT|lines=%s|bytes=%s\n' "$(wc -l < "$R" | tr -d ' ')" "$(wc -c < "$R" | tr -d ' ')"
printf '\n-- S1 BUILD DIRECTORIES --\n'
awk '
/-- BUILD DIRECTORIES/ { p=1; next }
/-- BUILD \/ MODEL/ { p=0 }
p { print }
' "$R"
printf '\n-- S1 UNIQUE ARCHIVE HASH GROUPS --\n'
awk -F'|' '
/-- SMALL NOX\/BRAIN ARCHIVE SHA-256/ { p=1; next }
/-- KNOWN SOURCE TREE MANIFEST ROOTS/ { p=0 }
p && NF >= 4 && $4 ~ /\.(zip|tgz|tar\.gz)$/ {
  h=$1; size[h]=$2; count[h]++; n=split($4,a,"/"); names[h]=(names[h] ? names[h] "," : "") a[n]
}
END { for (h in count) printf "%s|%s|%d|%s\n",h,size[h],count[h],names[h] }
' "$R" | LC_ALL=C sort
printf '\n-- S1 SOURCE TREE MANIFEST ROOT --\n'
grep '^TREE|' "$R" || true
