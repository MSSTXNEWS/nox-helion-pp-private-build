#!/bin/bash
ls /workspace/nox/web/site | head -20 | tr '\n' ' '; echo; ls /workspace/nox/web/pkg | head | tr '\n' ' '; echo; du -sh /workspace/nox/web
for p in 8104 8510 8520 8400 4000 8200; do echo "$p models: $(curl -s -m4 -H 'Accept-Encoding: identity' 127.0.0.1:$p/v1/models | head -c 220 | tr '\n' ' ')"; done
head -30 /workspace/nox/integration/adapter.py | cut -c1-160
