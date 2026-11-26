#!/bin/bash
python3 -c "
import json;d=json.load(open('/workspace/nox/state/judge_weights.json'));print(json.dumps(d,ensure_ascii=False)[:900])"
sed -n 424,462p /workspace/nox/judges/judge_service.py | cut -c1-220
