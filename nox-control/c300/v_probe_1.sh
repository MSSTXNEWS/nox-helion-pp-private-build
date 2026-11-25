echo "C300: v_probe_1"
ls /workspace/nox/state /workspace/nox/svc 2>&1 | head -40
cat /workspace/nox/svc/start_extra.sh | head -30
ls /workspace/nox/venv_living/bin 2>&1 | head -3; df -BG /workspace | tail -1
python3 --version; /workspace/nox/venv/bin/python --version
cat /workspace/nox/web/pkg/server/svc_registry.json | head -c 600
echo; ss -ltn | awk '{print $4}' | grep -o '[0-9]*$' | sort -n | tr '\n' ' '
echo
t(){ echo "== $1"; shift; curl -s -m 40 -w "\nHTTP %{http_code} %{time_total}s\n" "$@" | tail -c 500; }
t models-poll https://text.pollinations.ai/models
t poll-openai https://text.pollinations.ai/openai -H 'Content-Type: application/json' -d '{"model":"openai","messages":[{"role":"user","content":"Скажи привет по-русски"}]}'
t poll-get "https://text.pollinations.ai/Say%20hi%20in%20Russian?model=mistral"
t hf https://huggingface.co/api/spaces/Qwen/Qwen3-Demo
t hf2 https://huggingface.co
t openrouter https://openrouter.ai/api/v1/models -o /dev/null
t gh-models https://models.github.ai/catalog/models -o /dev/null
t groq https://api.groq.com/openai/v1/models
t cerebras https://api.cerebras.ai/v1/models
t ddg https://duckduckgo.com
