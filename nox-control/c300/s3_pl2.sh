#!/bin/bash
S=/workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/nox-planets3d.js?v=$(date +%s)" -o /tmp/s3pl.js && cp /tmp/s3pl.js $S/nox-planets3d.js && echo placed
ls $S/vendor/planets/2k | head -20
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
