#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import base64, gzip, os, pathlib, sys
p = pathlib.Path("/root/nox/v7_src_v6/nox_wow/CORES/CORE_PIPELINE_PROMPT.md")
packed = base64.b64encode(gzip.compress(p.read_bytes(), compresslevel=9, mtime=0)).decode("ascii")
part = int(os.environ.get("PART", "0"))
if part not in (0, 1):
    raise SystemExit("PART must be 0 or 1")
chunk = packed[part * 2100:(part + 1) * 2100]
print(f"PROMPT_B64_PART{part}:" + chunk)
print(f"PROMPT_B64_TOTAL:{len(packed)}")
PY
