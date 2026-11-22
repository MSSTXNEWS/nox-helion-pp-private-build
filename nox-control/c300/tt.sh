#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/tt.py -o /tmp/tt.py && /root/.nox-voice-venv/bin/python /tmp/tt.py
tr '\0' '\n' </proc/$(ss -ltnp | grep ':8094 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/environ | grep -E "NOX_(PIPER|XTTS|TTS)" | cut -c1-150
