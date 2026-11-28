echo "K1: hc5"
echo "load=$(cut -d' ' -f1-3 /proc/loadavg) cores=$(nproc)"
echo "h8104=$(curl -s -o /dev/null -m 3 -w %{http_code} http://127.0.0.1:8104/health) args=$(pgrep -af llama-server | grep -- '--port 8104' | grep -oE -- '(--n-cpu-moe|-np|--parallel|-ub|-b|--cache-reuse) [0-9]+' | tr '\n' ' ')"
t0=$(date +%s.%N); curl -s -m 60 http://127.0.0.1:8104/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"2+2?"}],"max_tokens":8,"chat_template_kwargs":{"enable_thinking":false}}' -o /dev/null -w "raw8104_code=%{http_code} ttfb=%{time_starttransfer}\n"
echo "br=$(pgrep -fc body_restart.sh) p5=$(pgrep -fc 'p5_') vram=$(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits)"
ps -eo pcpu,comm --sort=-pcpu | head -6 | awk '{print "cpu",$1,$2}'
echo END
