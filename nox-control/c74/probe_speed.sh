#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-1200; }
echo "== llama-server cmdline"; ps -eo pid,etime,args | grep "[l]lama-server" | grep 8098 | a
echo "== supervisor conf ds41"; grep -rh -A9 "program:nox-ds41-8098" /etc/supervisor/conf.d/ | grep -E "command|environment|autorestart|startsecs|stopwaitsecs" | a
echo "== llama bin version/flags"; /root/build/llama.cpp-sm70-build/bin/llama-server --version 2>&1 | head -2 | a
/root/build/llama.cpp-sm70-build/bin/llama-server --help 2>&1 | grep -E "^\s*(-fa|--flash-attn|--cache-reuse|--cache-type-k|--mlock|--no-mmap|-b,|-ub,|--threads|-t,|--threads-batch|--ctx-checkpoints|--slot-prompt|--parallel|--cont-batching|--no-warmup|--spec|--draft)" | cut -c1-150 | head -24
echo "== speed now"; curl -s -m 60 http://127.0.0.1:8098/props 2>/dev/null | head -c 400; echo
curl -s -m 90 http://127.0.0.1:8098/completion -d '{"prompt":"Привет, расскажи коротко про Москву.","n_predict":64,"cache_prompt":true}' | python3 -c "import sys,json;d=json.load(sys.stdin);t=d.get('timings',{});print('prompt_per_s',t.get('prompt_per_second'),'gen_per_s',t.get('predicted_per_second'),'n',t.get('predicted_n'))" 2>&1 | a
echo "== load/cpu"; uptime | a; free -g | awk 'NR==2{print "RAM",$2,$3,$4}'
