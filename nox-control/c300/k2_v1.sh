echo "C300: k2_v1"
N=/workspace/nox; ST=$N/state; F=$N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
curl -sI -m 20 https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf | grep -i "x-linked-etag" | tr -d '"\r' > $ST/k2_etag.txt; cat $ST/k2_etag.txt
[ -s $ST/k2_sha.txt ] || env RUNNER_TRACKING_ID=k2sha setsid -f nice -n 19 ionice -c3 bash -c "sha256sum $F > $ST/k2_sha.txt" </dev/null >/dev/null 2>&1
ls -la $F | cut -c20-80
echo "--- restart/measure log"; cat $ST/k2_restart.log | tail -6
echo "--- chat_fast.log tail"; tail -14 $ST/chat_fast.log | cut -c1-120
echo "--- slots"; curl -s -m5 localhost:8104/slots | python3 -c "import sys,json;[print(s['id'],s['is_processing'],len(str(s.get('prompt','')))) for s in json.load(sys.stdin)]"
echo "--- 8104 cmd"; tr '\0' ' ' < /proc/$(ss -ltnp | grep ':8104 ' | grep -o 'pid=[0-9]*' | cut -d= -f2)/cmdline | cut -c1-330; echo
uptime; ps -eo pid,ni,pcpu,args --sort=-pcpu | head -8 | cut -c1-140
