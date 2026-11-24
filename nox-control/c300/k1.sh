#!/bin/bash
grep -E "model_name|model:|api_base" /workspace/nox/router/config.yaml | head -30 | cut -c1-120
for p in 8104 8106 8200 8500 8510 8520 8300 8301 8400 8120 8130 8888 4100 4210 4220; do echo "$p $(curl -s -m3 -o /tmp/p.b -w %{http_code} 127.0.0.1:$p/ ) $(head -c 90 /tmp/p.b | tr '\n' ' ')"; done
for p in 8500 8510 8520 8300 8400; do echo "$p: $(tr '\0' ' ' < /proc/$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cmdline | cut -c1-140)"; done
ls /workspace/nox | tr '\n' ' '; echo; df -h /workspace | tail -1; ls /workspace/nox/web 2>/dev/null | head -5
