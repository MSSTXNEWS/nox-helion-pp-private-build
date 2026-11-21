#!/bin/bash
R=/root/nox/repo; git -C $R pull -q 2>&1 | tail -1
timeout 100 bash $R/nox-control/c122/boot_s1.sh 2>&1 | tail -8 | cut -c1-200
pgrep -af "gateway.py|llama-server" | cut -c1-150
sleep 3; curl -s -m 60 http://127.0.0.1:8082/v1/chat/completions -H 'content-type: application/json' -d '{"model":"nox","stream":false,"messages":[{"role":"user","content":"Где ты сейчас работаешь и на какой модели?"}]}' | head -c 600; echo
