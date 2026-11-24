#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/tt.py -o /tmp/tt.py && /workspace/nox/voice_venv/bin/python /tmp/tt.py 2>&1 | cut -c1-220
ls /workspace/nox/voice_models; grep -n "PORT\|port" /workspace/nox/brain/GROW/awaken/growth_dashboard.py | head -3 | cut -c1-140
