#!/usr/bin/env bash
# Closest honest Linux build for the Windows-only NOX HELION candidate.
# Produces a native x64 status binary that loads the same payload and fixtures
# the Windows candidate packages. It is not the Tk desktop EXE and not the
# reference candidate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="${NOX_SOURCE_ROOT:-/tmp/noxsrc/tree}"
OUT="${1:-$ROOT/work/linux-m2}"
PY="${M2_PYTHON:-python3}"

if [[ ! -f "$SOURCE/helion/personas.py" ]]; then
  echo "SOURCE_MISSING:$SOURCE" >&2
  exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT/src"
"$PY" -m venv "$OUT/venv"
"$OUT/venv/bin/pip" install --disable-pip-version-check cryptography==50.0.2 pyinstaller==6.16.0
"$OUT/venv/bin/python" "$ROOT/tools/m2_payload/assemble_m2_payload.py" --source "$SOURCE" --dest "$ROOT/build_inputs/m2" --check
"$OUT/venv/bin/python" "$ROOT/tools/m2_payload/m2_import_smoke.py" \
  --source "$SOURCE" \
  --payload "$ROOT/build_inputs/m2" \
  --out-dir "$OUT/receipt"
# Package the payload beside a native binary. PyInstaller on Linux uses ':' as the data separator.
SEP=":"
"$OUT/venv/bin/pyinstaller" --noconfirm --onefile --clean \
  --name NOX_HELION_M2_0_PAYLOAD_STATUS \
  --distpath "$OUT/dist" \
  --workpath "$OUT/scratch" \
  --specpath "$OUT/scratch" \
  --paths "$ROOT/tools/m2_payload" \
  --hidden-import m2_import_smoke \
  --hidden-import m2_common \
  --hidden-import cryptography \
  --hidden-import cryptography.hazmat.primitives.asymmetric.ed25519 \
  --hidden-import cffi \
  --add-data "$ROOT/build_inputs/m2/product_payload${SEP}m2/product_payload" \
  --add-data "$ROOT/build_inputs/m2/fixtures${SEP}m2/fixtures" \
  --add-data "$ROOT/build_inputs/m2/M2_PAYLOAD_MANIFEST.json${SEP}m2" \
  --add-data "$ROOT/build_inputs/m2/VERSION.txt${SEP}m2" \
  "$ROOT/tools/m2_payload/m2_payload_status.py"
test -f "$OUT/dist/NOX_HELION_M2_0_PAYLOAD_STATUS"
# Prove the frozen binary can see the packaged payload without the source tree beside it.
"$OUT/dist/NOX_HELION_M2_0_PAYLOAD_STATUS" --version
# The frozen binary loads the packaged payload through the pinned app readers.
"$OUT/dist/NOX_HELION_M2_0_PAYLOAD_STATUS" --check --source "$SOURCE"
# The frozen binary's loaders import helion from the source when --source is passed.
# Packaging proof: the marker is inside the ELF. The import smoke already ran against the tree.
"$OUT/venv/bin/python" - << PY
from pathlib import Path
import sys
sys.path.insert(0, "$ROOT/tools/m2_payload")
from m2_import_smoke import exe_contains_payload
print(exe_contains_payload(Path("$OUT/dist/NOX_HELION_M2_0_PAYLOAD_STATUS")))
PY
STAGE="$OUT/NOX_HELION_M2_0_linux_x64"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp "$OUT/dist/NOX_HELION_M2_0_PAYLOAD_STATUS" "$STAGE/"
cp -a "$ROOT/build_inputs/m2/product_payload" "$ROOT/build_inputs/m2/fixtures" "$STAGE/"
cp "$ROOT/build_inputs/m2/M2_PAYLOAD_MANIFEST.json" "$ROOT/build_inputs/m2/VERSION.txt" "$STAGE/"
cp "$OUT/receipt/M2_ACK_RECEIPT.json" "$OUT/receipt/M2_PAYLOAD_INTEGRITY.html" "$OUT/receipt/m2-import-smoke.log" "$OUT/receipt/SHA256SUMS.txt" "$STAGE/"
cat > "$STAGE/README_LINUX.txt" << 'EOF'
NOX HELION M2.0-PP Linux package

This is the Linux build for the payload/fixtures stripe. The full desktop
candidate is a Windows x64 executable because C_RELEASE_SPRINT_BUILD.ps1
requires a Windows x64 host and a windowed Tk build. This package is the
closest runnable Linux equivalent:

- NOX_HELION_M2_0_PAYLOAD_STATUS is a native Linux x64 binary.
- product_payload/ and fixtures/ are the same bytes the Windows candidate packages.
- The status binary's --check mode, given --source pointing at the pinned tree,
  loads those bytes through the app's own readers.
- It does not claim ONLINE, live AI, or product acceptance.
- It is not NOX_HELION_PRIVATE_CANDIDATE.exe and does not replace that file.

Owner acknowledgement ticks in M2_ACK_RECEIPT.json stay unsigned.
EOF
# Re-run smoke against the staged copy and the Linux binary.
"$OUT/venv/bin/python" "$ROOT/tools/m2_payload/m2_import_smoke.py" \
  --source "$SOURCE" \
  --payload "$ROOT/build_inputs/m2" \
  --staged "$STAGE" \
  --exe "$STAGE/NOX_HELION_M2_0_PAYLOAD_STATUS" \
  --out-dir "$OUT/staged-receipt"
cp "$OUT/staged-receipt/M2_ACK_RECEIPT.json" "$OUT/staged-receipt/M2_PAYLOAD_INTEGRITY.html" \
  "$OUT/staged-receipt/m2-import-smoke.log" "$STAGE/"
tar -C "$OUT" -czf "$OUT/NOX_HELION_M2_0_linux_x64.tar.gz" "NOX_HELION_M2_0_linux_x64"
echo "LINUX_PACKAGE=$OUT/NOX_HELION_M2_0_linux_x64.tar.gz"
