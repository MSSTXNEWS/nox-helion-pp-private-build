#!/usr/bin/env bash
set -euo pipefail

ROOT=/root/nox
OUT=/tmp/nox_build_inventory_20261122.txt
if [[ ! -d "$ROOT" ]]; then
  echo "NO_ROOT $ROOT"
  exit 2
fi
: > "$OUT"
{
  printf 'S1_NOX_INVENTORY_UTC|%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'ROOT|%s\n' "$ROOT"
  printf '\n-- BUILD DIRECTORIES (depth <= 3) --\n'
  find "$ROOT" -xdev -mindepth 1 -maxdepth 3 -type d \
    \( -iname '*nox*' -o -iname '*brain*' -o -iname '*kernel*' -o -iname '*build*' -o -iname '*dataset*' -o -iname '*checkpoint*' -o -iname '*adapter*' -o -iname '*trainer*' -o -iname '*v[0-9]*' \) \
    -printf '%TY-%Tm-%TdT%TH:%TM:%TSZ|%p\n' | sort
  printf '\n-- BUILD / MODEL / MANIFEST FILES (depth <= 7) --\n'
  find "$ROOT" -xdev -maxdepth 7 -type f \
    \( -iname '*.zip' -o -iname '*.tar' -o -iname '*.tar.gz' -o -iname '*.tgz' -o -iname '*.gguf' -o -iname '*.safetensors' -o -iname '*.npz' -o -iname '*.pt' -o -iname '*.pth' -o -iname '*.ckpt' -o -iname '*manifest*' -o -iname '*sha256*' -o -iname '*checkpoint*' -o -iname '*dataset*' \) \
    -printf '%TY-%Tm-%TdT%TH:%TM:%TSZ|%s|%p\n' | sort
  printf '\n-- SMALL NOX/BRAIN ARCHIVE SHA-256 (<=200 MiB) --\n'
  while IFS= read -r -d '' f; do
    printf '%s|' "$(sha256sum "$f" | awk '{print $1}')"
    stat -c '%s|%y|%n' "$f"
  done < <(find "$ROOT" -xdev -maxdepth 7 -type f \
    \( -iname '*.zip' -o -iname '*.tar.gz' -o -iname '*.tgz' \) \
    \( -iname '*nox*' -o -iname '*brain*' -o -iname '*v[0-9]*' \) \
    -size -200M -print0 | sort -z)
  printf '\n-- KNOWN SOURCE TREE MANIFEST ROOTS --\n'
  for d in "$ROOT/v7_src_v6/nox_wow" "$ROOT/v7_src_v6/KERNEL_100"; do
    if [[ -d "$d" ]]; then
      mf="/tmp/$(basename "$d")_inventory_20261122.sha256"
      (cd "$d" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$mf"
      printf 'TREE|%s|files=%s|bytes=%s|manifest_sha256=%s\n' \
        "$d" "$(wc -l < "$mf" | tr -d ' ')" "$(du -sb "$d" | awk '{print $1}')" "$(sha256sum "$mf" | awk '{print $1}')"
    fi
  done
  printf '\n-- END --\n'
} >> "$OUT"
tail -c 2800 "$OUT"
