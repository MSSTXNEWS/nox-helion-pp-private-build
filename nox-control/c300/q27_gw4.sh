echo "K1: q27_gw4"
export RUNNER_TRACKING_ID=""
G=/workspace/nox/advisors/gateway.py
grep -nE "^ST *=" $G | cut -c1-100
ST=$(python3 -c "
import re;s=open('$G',encoding='utf-8').read();m=re.search(r'^ST\s*=\s*(.+)$',s,re.M);print(m.group(1))" | sed -E "s/^os\.environ\.get\('[A-Z_]+', *'([^']+)'\).*/\1/;s/^'([^']+)'.*/\1/"); echo "ST=$ST" | sed 's#/workspace/nox#N#'
E=$ST/secrets/advisors.env; [ -f $E ] && echo "envfile size=$(wc -c < $E)" || echo "envfile missing"
for n in GROQ_API_KEY CEREBRAS_API_KEY GEMINI_API_KEY OPENROUTER_API_KEY MISTRAL_API_KEY GITHUB_MODELS_TOKEN; do echo "$n $(grep -E "^$n=.+" $E 2>/dev/null | wc -l)"; done
echo "litellm cmd: $(ps -eo args | grep 'bin/litellm' | grep -v grep | grep -oE -- '--(host|port) [^ ]+|--config [^ ]+' | tr '\n' ' ' | sed 's#/workspace/nox#N#g')"
pid=$(pgrep -f "bin/litellm" | head -1); echo "litellm pid=$pid listen=$(ss -ltnp | grep "pid=$pid," | awk '{print $4}' | tr '\n' ' ')"; echo "uptime_s=$(ps -o etimes= -p $pid 2>/dev/null)"
cfg=/workspace/nox/router/config.yaml; echo "router cfg models: $(grep -c 'model_name' $cfg) providers: $(grep -oE 'model: [a-z_]+/' $cfg | sort | uniq -c | tr '\n' ' ')"
for p in 4000 4200 4210 4211 4220; do echo "port $p $(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/health/liveliness)"; done
grep -n "4210" /workspace/nox/router/*.y*ml 2>/dev/null | head -3 | cut -c1-120
grep -rn "4210" /workspace/nox/supervisor 2>/dev/null | head -3 | cut -c1-140
echo END
