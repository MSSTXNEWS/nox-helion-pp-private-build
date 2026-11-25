#!/bin/bash
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server
echo "#### nox_cmd.py size"; wc -l $P/nox_cmd.py; grep -n "def \|builtin\|svc_registry" $P/nox_cmd.py | head -30
echo "#### svc_registry"; grep -rn "svc_registry\|SVC_REG\|restart" $P/*.py /workspace/nox/web/pkg/*.py 2>/dev/null | cut -c1-200 | head -15; ls /workspace/nox/web/pkg | head -20
echo "#### reg cmds"; /workspace/nox/venv/bin/python -c "
import json;r=json.load(open('$S/qa/registry.json'));print(list(r['commands'].keys()))"
echo "#### run_web"; cat $P/run_web.sh | head -20
echo "#### meili"; curl -s -m 5 localhost:7700/health; echo; curl -s -m 5 localhost:7700/version | head -c 200; echo; ps aux | grep -i meili | grep -v grep | cut -c1-150 | head -2
echo "#### vendor"; ls $S/vendor | tr '\n' ' '; ls /workspace/nox/web/build/node_modules 2>/dev/null | grep -i "mediapipe\|nosleep\|cmdk\|lightweight\|gsap" | tr '\n' ' '
echo; ls /workspace/nox/web/build/node_modules/@mediapipe 2>/dev/null
curl -s -m 5 -o /dev/null -w "ntfy %{http_code}\n" -d "test" localhost:2586/nox-helion
