#!/bin/bash
cd /workspace/nox/nox-control/c300 2>/dev/null || cd $(dirname $0)
P=$(find / -name s5_patch_handmade.py -path "*c300*" 2>/dev/null | head -1); echo "patch=$P"
/workspace/nox/venv/bin/python $P /workspace/nox/qa_audit.py /workspace/nox/web/site/qa/registry.json
grep -c HANDMADE /workspace/nox/qa_audit.py; grep -n '"text"\|checklist' /workspace/nox/web/site/qa/registry.json | head -3
python3 -c "import json;print(json.load(open('/workspace/nox/web/site/qa/registry.json'))['checklist'][-2:])"
