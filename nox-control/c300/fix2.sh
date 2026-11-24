#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/fix2.py -o /tmp/fix2.py && /workspace/nox/venv/bin/python /tmp/fix2.py
for u in /web/tools.html /web/tv.html /web/nox-tools.js /web/vendor/nox-x/monaco/min/vs/loader.js /web/vendor/nox-x/excalidraw/dist/excalidraw.production.min.js; do echo "$u $(curl -s -m8 -o /dev/null -w %{http_code} 127.0.0.1:8091$u)"; done
