#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/au.py -o /tmp/au.py && /workspace/nox/venv/bin/python /tmp/au.py 2>&1 | head -70
pgrep -af "drive_media|bridge.py" | cut -c1-150; ss -ltnp | grep -E "python.*(bridge)" | head -3
