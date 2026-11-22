#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/nox/v7_src_v6/nox_wow
PROMPT="$ROOT/CORES/CORE_PIPELINE_PROMPT.md"
ZIP=/root/nox/in_v6/NOX_V7_BRAIN_v6_20261122.zip
printf 'CORE_PREFLIGHT_BEGIN\n'
test -d "$ROOT"
test -s "$PROMPT"
test -s "$ZIP"
printf 'prompt_bytes='; wc -c < "$PROMPT"
printf 'prompt_sha256='; sha256sum "$PROMPT" | awk '{print $1}'
printf 'source_zip_sha256='; sha256sum "$ZIP" | awk '{print $1}'
printf 'core_files:\n'
find "$ROOT/CORES" -maxdepth 2 -type f -printf '%P\t%s bytes\n' | sort | head -60
printf 'prompt_path_refs:\n'
grep -Eo 'nox_wow/[[:alnum:]_./-]+' "$PROMPT" | sort -u | head -50 || true
printf 'required_files='
for f in "$ROOT/CORES/CORE_1M.md" "$ROOT/CORES/SCHEMA.md" "$ROOT/CORES/registry.tsv" "$ROOT/CATALOGS/CORE_SOURCES.md" "$ROOT/SPRINT3D/banks.json" "$ROOT/SEED/core_distill.py"; do
  test -s "$f" && printf 'OK ' || printf 'MISSING '
  printf '%s ' "${f#"$ROOT"/}"
done
printf '\nresources:\n'
df -h /root /dev/shm
free -g
printf 'CORE_PREFLIGHT_END\n'
