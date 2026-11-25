#!/bin/bash
P=/workspace/nox/svc/podcastfy/venv/lib/python3.11/site-packages/podcastfy
sed -n 96,122p $P/api/fast_app.py; sed -n 55,100p $P/content_generator.py
grep -n "openai" $P/tts/providers/openai.py | head; which ffmpeg
curl -s -m5 http://127.0.0.1:8091/svc/podcastfy/healthcheck -w " %{http_code}\n"; curl -s -m3 http://127.0.0.1:8104/v1/models -o /dev/null -w "8104 %{http_code}\n"
