echo "C300: k2_a1"
N=/workspace/nox; O=$N/agent/out
echo "--- baseline bind errs: 8301=$(grep -c 'already in use' $O/adapter_mem_8301.log) 8090=$(grep -c 'already in use' $O/core_8090.log)"
echo "--- T3: memadp.lock"; touch $N/state/locks/memadp.lock; ls -la $N/state/locks | tail -4
echo "--- T4: GB10 tunnel off"; touch $N/state/gb10_judge_tunnel.off
for p in $(pgrep -f gb10_judge_tunnel.sh); do kill $p 2>/dev/null; done; pkill -f "nox_gb10_judge.*18100" 2>/dev/null; sleep 1; pgrep -af gb10_judge | cut -c1-100
echo "--- T4: web_chat tunnel stop"; supervisorctl stop nox_web_chat_tunnel 2>&1 | head -2; pgrep -af "tunnel --no-autoupdate --url http://127.0.0.1:18091" | cut -c1-100
echo "--- T5: meili index fix"
cp -n $N/svc/nox_index.py $N/svc/nox_index.py.bak_k2
python3 - <<'P'
f="/workspace/nox/svc/nox_index.py"; s=open(f).read()
a='try:\n    mreq("/indexes", {"uid": "nox", "primaryKey": "id"})\nexcept Exception: pass'
b='try:\n    mreq("/indexes/nox")\nexcept Exception:\n    try: mreq("/indexes", {"uid": "nox", "primaryKey": "id"})\n    except Exception: pass'
print("patched" if a in s else "pattern-missing"); open(f,"w").write(s.replace(a,b))
P
echo "--- T6: invokeai"
ss -Htn state established "( dport = :9090 )" | wc -l
pkill -f "invokeai-web --root" ; sleep 3; pgrep -af invokeai-web | cut -c1-80; nvidia-smi --query-gpu=memory.used --format=csv,noheader
echo "--- T6: registry 8143"; sed -n 105,140p $N/stewards/orch_registry.json | cut -c1-200
echo "--- T7: start download"
D=$N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF; F=$D/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
pgrep -f "Thinking-2507-Q4_K_M.gguf" | grep -v $$ >/dev/null && echo "dl already running" || {
 env RUNNER_TRACKING_ID=k2dl setsid -f nice -n 19 ionice -c3 bash -c "for i in 1 2 3 4 5 6 7 8; do curl -fL -C - --retry 5 --retry-delay 10 -o '$F' https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf >> $N/state/k2_dl_thinking.log 2>&1 && break; sleep 20; done; echo done \$(stat -c %s '$F') >> $N/state/k2_dl_thinking.log" </dev/null >/dev/null 2>&1
 sleep 20; ls -la $F | cut -c20-80; tail -c 200 $N/state/k2_dl_thinking.log | tr '\r' '\n' | tail -2; }
