echo "K1: q27_scan"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "self_now.json: $(ls -l $N/state/core/self_now.json 2>&1 | awk '{print $5}') keys: $(python3 -c "import json;d=json.load(open('$N/state/core/self_now.json'));print(sorted(d)[:15] if isinstance(d,dict) else type(d))" 2>&1 | cut -c1-200)"
for f in api_bridge.py canon.py chat_core.py; do for p in $(find $N -name $f -not -path "*/node_modules/*" 2>/dev/null | head -3); do echo "$p self_now=$(grep -c self_now $p) feeling=$(grep -c feeling $p) МСК=$(grep -c -E 'Moscow|МСК|UTC\+3' $p)"; done; done
echo "state/mind: $(ls $N/state/mind 2>&1 | head -20 | tr '\n' ' ')"
echo "feeling logs: $(ls $N/state | grep -i feel | tr '\n' ' ')"
echo "sensorium: $(find $N -name 'sensorium*.json' 2>/dev/null | head -3 | tr '\n' ' ')"; python3 $N/mods/sensorium_ext.py --help 2>&1 | head -8 | cut -c1-160
echo "control_vectors: $(find $N -name 'control_vectors*' 2>/dev/null | head -3 | tr '\n' ' ')"
echo "board.mode: $(grep -rl 'board.mode\|board_mode' $N/state $N/mods 2>/dev/null | head -3 | tr '\n' ' ')"
echo "gateway procs:"; ps -eo args | grep -E "nox_tools_gateway|8793" | grep -v grep | sed 's/--[a-z-]*key[= ][^ ]*/--KEY/;s/sk-[A-Za-z0-9]*/KEY/g' | cut -c1-150
G=$(find $N /home -name "nox_tools_gateway*" -not -path "*/node_modules/*" 2>/dev/null | head -5); echo "gw files: $G"
for g in $G; do [ -f $g ] && echo "$g lines=$(wc -l < $g) lcoder=$(grep -c lcoder $g) 403=$(grep -c 403 $g) allow_personal=$(grep -c allow_personal $g)"; done
echo "key env presence:"; for k in GROQ_API_KEY CEREBRAS_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY; do v=$(tr '\0' '\n' < /proc/$(ss -ltnp | grep '127.0.0.1:8793 ' | sed 's/.*pid=\([0-9]*\).*/\1/')/environ 2>/dev/null | grep -c "^$k=."); echo "$k=$v"; done
ls $N/state/keys 2>/dev/null | sed 's/\..*//' | sort | head -20 | tr '\n' ' '; echo
echo "models on disk:"; find / -xdev \( -iname "*huihui*" -o -iname "*t-pro*" -o -iname "*tpro*" \) \( -name "*.gguf" -o -type d \) 2>/dev/null | head -8 | sed 's#.*/##'
ls $N/models 2>/dev/null | head -30 | tr '\n' ' '; echo
ss -ltnp | grep -oE "127.0.0.1:81[0-9]{2}" | sort -u | tr '\n' ' '; echo
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | head -1
grep -n "advisor1\|n_probs\|logprobs" $N/web/pkg/server/chat_core.py | wc -l
ls $N/state/chat_advisor1.off 2>&1 | tail -1
echo END
