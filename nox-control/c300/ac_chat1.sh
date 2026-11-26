echo "C300: ac_chat1"
P=$(pgrep -f "port 8104" | head -1); tr '\0' ' ' </proc/$P/cmdline; echo; echo "aff $(taskset -cp $P|sed 's/.*: //') ni $(ps -o ni= -p $P) rss $(ps -o rss= -p $P)"
B=/workspace/nox/bin/llama-server; $B --version 2>&1 | head -3
$B --help 2>&1 | grep -iE "^ *(-md|--spec|--draft|--cache-reuse|-ctk|--mlock|-ub|-fa|--flash|--mtp|--threads-batch|--no-mmap)" | cut -c1-140 | head -20
lscpu | grep -E "Model name|Flags" | cut -c1-60; lscpu | grep -oE "avx512[a-z_0-9]*|avx2|amx[a-z_0-9]*" | sort -u | tr '\n' ' '; echo
ls /workspace/nox/state | grep -iE "owner|live" ; ls /workspace/nox/state/*LIVE* /workspace/nox/state/*OWNER* 2>/dev/null
curl -s -m 3 127.0.0.1:8104/slots | python3 -c "import sys,json;print([(s['id'],s['is_processing'],s.get('n_ctx')) for s in json.load(sys.stdin)])"
curl -s -m 3 127.0.0.1:8104/props | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ('model_alias','total_slots','build_info')})"
find /workspace/nox/models -iname "*0.6B*gguf" -o -iname "*Qwen3-0.6B*GGUF" 2>/dev/null | head -4
free -g | head -2; uptime
