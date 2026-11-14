#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo 'NOX V38 STAGE ONLY - no service/model/data changes'
python3 - <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path.cwd()
manifest=json.loads((root/'FILES_SHA256.json').read_text('utf8'))
missing=[];wrong=[]
for rel,dig in manifest.items():
 p=(root/rel).resolve()
 if not p.is_relative_to(root.resolve()) or not p.is_file():missing.append(rel);continue
 if hashlib.sha256(p.read_bytes()).hexdigest()!=dig:wrong.append(rel)
if missing or wrong:
 print('SOURCE_SHA_HOLD',{'missing':missing,'wrong':wrong});sys.exit(4)
print('SOURCE_SHA_PASS',len(manifest))
PY
PYTHONPATH=. python3 -m unittest discover -s nox_runpod/teacher_mesh/v38/tests -t . -v
echo 'SOURCE_ONLY_ACCEPTED; NOX NOT DEPLOYED'
