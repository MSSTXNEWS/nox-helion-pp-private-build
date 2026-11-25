echo "C300: a2_probe9"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/a5df083761eca86a473a88afc7930d02685ee5c3/nox-control/c300; A=/workspace/nox/agents
cat $A/measure_before.log | cut -c1-500
curl -fsSL "$R/v_gw_gateway.py" -o /tmp/gw_repo.py; echo "== diff server vs repo"; diff /tmp/gw_repo.py /workspace/nox/advisors/gateway.py | cut -c1-260 | head -40
echo "== llm7 anon token"; for m in gpt-oss-20b Qwen3.8-Flash mistral-Nemo-Instruct-2407; do curl -s -m 30 https://api.llm7.io/v1/chat/completions -H 'Authorization: Bearer unused' -H 'Content-Type: application/json' -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"скажи ок\"}],\"max_tokens\":8}" | head -c 200; echo; done
echo "== pollinations"; for m in openai-fast openai mistral; do curl -s -m 40 https://text.pollinations.ai/openai -H 'Content-Type: application/json' -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"скажи ок\"}],\"max_tokens\":8}" | head -c 160; echo; done
echo "== gradio_client"; $A/venv/bin/pip install -q gradio_client 2>&1 | tail -1
timeout 90 $A/venv/bin/python - <<'P'
try:
    from gradio_client import Client
    for sp in ('Qwen/Qwen2.5-72B-Instruct','Qwen/Qwen3-Demo','Qwen/Qwen2.5-Max-Demo'):
        try:
            c = Client(sp, verbose=False); print(sp, 'OK endpoints', list(c.view_api(return_format='dict')['named_endpoints'])[:4])
        except Exception as e: print(sp, 'нет:', str(e)[:100])
except Exception as e: print('gradio_client ERR', e)
P
