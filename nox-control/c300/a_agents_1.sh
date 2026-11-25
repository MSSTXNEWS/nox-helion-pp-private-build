# A: разведка для субисполнителей (только чтение)
echo "== GPU"; nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv 2>&1 | head -3
echo "== DISK"; df -h /workspace /home 2>&1 | head -4
echo "== RAM"; free -g | head -2
echo "== PORTS"; ss -ltnp 2>/dev/null | awk '{print $4}' | sort -u | tr '\n' ' '
echo; echo "== llama-swap"; curl -s -m 5 127.0.0.1:8200/running | head -c 600; echo; curl -s -m 5 127.0.0.1:8200/v1/models | head -c 800; echo
echo "== proxy"; curl -s -m 5 127.0.0.1:8091/glm/v1/models | head -c 400; echo
echo "== llama-swap cfg"; ls /workspace/nox/*swap* /workspace/nox/**/llama-swap*.y* 2>/dev/null; find /workspace -maxdepth 3 -name '*swap*.y*ml' 2>/dev/null | head
for f in $(find /workspace -maxdepth 3 -name '*swap*.y*ml' 2>/dev/null | head -2); do echo "-- $f"; head -60 $f; done
echo "== models dir"; find /workspace -maxdepth 3 -name '*.gguf' -size +100M 2>/dev/null | head -20 | xargs -r ls -la
echo "== py pkgs"; python3 --version; pip list 2>/dev/null | grep -iE 'smolagents|aider|openai|flask|fastapi|uvicorn|requests|pytest|playwright' 
echo "== svc_registry"; find /workspace/nox -maxdepth 3 -iname '*svc_registry*' 2>/dev/null | head; 
echo "== start_extra"; find /workspace -maxdepth 3 -name 'start_extra.sh' 2>/dev/null | head -2 | while read f; do echo $f; tail -25 $f; done
echo "== arbiter"; cat /workspace/nox/state/arbiter.json 2>&1 | head -c 800; echo; ls /workspace/nox/state | head -50
echo "== keys (только имена)"; env | grep -iE 'openrouter|groq|gemini|cerebras|mistral' | sed 's/=.*/=<set>/'; ls /workspace/nox/state/*key* /workspace/nox/secrets 2>/dev/null | head
echo "== net"; curl -s -m 8 -o /dev/null -w 'hf %{http_code}\n' https://huggingface.co; curl -s -m 8 -o /dev/null -w 'pypi %{http_code}\n' https://pypi.org/simple/smolagents/
