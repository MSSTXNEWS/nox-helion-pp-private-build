#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import base64, gzip, pathlib, sys
p = pathlib.Path("/root/nox/v7_src_v6/nox_wow/CORES/CORE_PIPELINE_PROMPT.md")
data = p.read_bytes()
packed = base64.b64encode(gzip.compress(data, compresslevel=9, mtime=0)).decode("ascii")
if len(packed) > 2800:
    print("PROMPT_PACKED_TOO_LARGE", len(packed))
    sys.exit(2)
print("PROMPT_GZIP_B64:" + packed)
PY
