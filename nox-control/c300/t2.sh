#!/bin/bash
V=/root/nox/repo/nox-control/voice; grep -n "def do_\|path ==\|startswith(\"/\|elif p\|if p ==\|out_rate\|sample_rate\|voice\b\|\.onnx\|speaker_wav\|language" $V/tts_server.py | head -40 | cut -c1-170
grep -n "def do_\|path ==\|if p ==\|elif p" $V/stt_server.py 2>/dev/null | head -10 | cut -c1-150
