cd /workspace/nox
echo "== arbiter 60-100"; sed -n 55,100p agent/arbiter.py
echo "== judge /judge schema"; sed -n 340,372p judges/judge_service.py; curl -s -m 5 127.0.0.1:8300/judges | head -c 700; echo
echo "== who serves chat"; grep -rnE '8104|8091|8200' web/pkg/server/*.py 2>/dev/null | grep -iE 'chat|turn|llama|upstream' | head -8 | cut -c1-220
echo "== nox_cmd head"; grep -nE '^def |COMMANDS|"/' web/pkg/server/nox_cmd.py | head -25 | cut -c1-180
echo "== svc_registry sample"; head -c 500 web/pkg/server/svc_registry.json; ls web/pkg/server/*.bak_d_1 2>&1 | head -1
echo "== free ports"; for p in 8810 8811 8815; do (echo >/dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "$p busy" || echo "$p free"; done
echo "== 8143/8141/8142/8106 alive"; for p in 8141 8142 8143 8106 8152 8151; do echo "$p $(curl -s -m 3 -o /dev/null -w '%{http_code}' 127.0.0.1:$p/health)"; done
echo "== venv+pkgs"; mkdir -p /workspace/nox/agents && python3 -m venv /workspace/nox/agents/venv 2>&1 | tail -1; /workspace/nox/agents/venv/bin/pip install -q langgraph huey httpx fastapi 'uvicorn[standard]' pytest 2>&1 | tail -2; /workspace/nox/agents/venv/bin/pip list 2>/dev/null | grep -iE 'langgraph|huey|fastapi|uvicorn|httpx|pytest' | tr '\n' ' '
echo; echo "== downloads (free GB: $(df -BG --output=avail /workspace | tail -1))"
mkdir -p /workspace/nox/models/agents/coder3b /workspace/nox/models/agents/trainer17b
cd /workspace/nox/models/agents
dl(){ [ -s "$2" ] && echo "have $2" || curl -sL -m 900 --fail -o "$2.part" "$1" && mv "$2.part" "$2"; ls -la "$2"; }
dl https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf coder3b/qwen2.5-coder-3b-instruct-q4_k_m.gguf
dl https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf trainer17b/Qwen3-1.7B-Q4_K_M.gguf
df -h /workspace | tail -1
