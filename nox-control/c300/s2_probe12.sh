#!/bin/bash
grep -n -i podcastfy /workspace/nox/svc/start_extra.sh /workspace/nox/svc/start_all.sh /workspace/nox/svc/start_d.sh | cut -c1-300
P=$(ls -d /workspace/nox/svc/podcastfy/venv/lib/python*/site-packages/podcastfy)
echo $P; sed -n 1,400p $P/api/fast_app.py | grep -n "def \|transcript\|llm_model\|api_key\|tts_model\|base" | head -50
grep -n "ChatLiteLLM\|ChatOpenAI\|api_base\|base_url\|is_local\|def __init__\|llm_model_name" $P/content_generator.py | head -40
grep -n "base_url\|OpenAI(" $P/tts/providers/openai.py | head
