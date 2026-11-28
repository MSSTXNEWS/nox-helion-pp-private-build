echo "K1: q27_scan2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
for port in 8793 8300 8105 8120 8130 8141 8142 8151 8152 8187; do pid=$(ss -ltnp | grep "127.0.0.1:$port " | sed 's/.*pid=\([0-9]*\).*/\1/'); echo "$port pid=$pid exe=$(readlink /proc/$pid/exe | sed 's#.*/##') args=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -oE '[^ /]*\.(py|gguf)|--(ctx-size|n-gpu-layers|alias|control-vector[a-z-]*) [^ ]*|-c [0-9]+' | tr '\n' ' ' | cut -c1-180)"; done
gp=$(ss -ltnp | grep '127.0.0.1:8793 ' | sed 's/.*pid=\([0-9]*\).*/\1/'); gf=$(tr '\0' '\n' < /proc/$gp/cmdline | grep -E '\.py$' | head -1); echo "gw_script=$gf"
if [ -f "$gf" ]; then echo "lines=$(wc -l < $gf) lcoder=$(grep -c lcoder $gf) 403=$(grep -c '403' $gf) personal=$(grep -c personal $gf) key_refs=$(grep -ciE 'api_key|_KEY' $gf)"; grep -n "403" $gf | head -5 | sed 's/\(.\{0,140\}\).*/\1/' | sed -E 's/(sk|gsk|AIza)[A-Za-z0-9_-]+/KEY/g'; D=$(dirname $gf); ls $D | head -20 | tr '\n' ' '; echo; for f in $D/*.json $D/*.yaml $D/*.yml $D/*.env; do [ -f $f ] && echo "cfg $(basename $f) size=$(wc -c < $f) keyfields=$(grep -ciE 'key|token|secret' $f)"; done 2>/dev/null; fi
echo "key files (names only, nonempty):"; find $N/state/keys $N/secrets /etc/nox ~/.config/nox 2>/dev/null -maxdepth 2 -type f -size +0 | sed 's#.*/##' | grep -viE "pem|ssh" | head -20 | tr '\n' ' '; echo
echo "groq/cerebras/gemini key strings in gateway dir: $(grep -rlE 'gsk_[A-Za-z0-9]{10}|AIza[A-Za-z0-9_-]{10}|csk-[A-Za-z0-9]{10}' $(dirname $gf) 2>/dev/null | wc -l)"
echo "ROLES: $(python3 -c "import json;d=json.load(open('$N/models/ROLES.json'));print(json.dumps(d)[:900])" 2>&1 | sed -E 's#/[^" ]*/##g')"
echo "gguf: $(find $N/models -name '*.gguf' 2>/dev/null | sed 's#.*/##' | head -25 | tr '\n' ' ')"
echo "self_now keys sample: $(python3 -c "import json;d=json.load(open('$N/state/core/self_now.json'));print(type(d['feelings']).__name__,len(d['feelings']),list(d['telemetry'])[:6],len(d['text']),d['training'])" 2>&1)"
echo "api_bridge self_now: $(grep -n self_now $N/ops/api_bridge/api_bridge.py | cut -c1-160)"
echo "canon self_now: $(grep -n self_now $N/canon/canon.py | cut -c1-160)"
echo "ext usage: $(grep -n 'argv\|--merge\|def main' $N/mods/sensorium_ext.py | head -8 | cut -c1-140)"
echo "sensors now: $(python3 -c "import json;d=json.load(open('$N/canon/sensorium.json'));print(type(d).__name__,len(d),list(d)[:5])" 2>&1 | cut -c1-200)"
echo "cv: $(python3 -c "import json;d=json.load(open('$N/state/mind/control_vectors.json'));print(json.dumps({k:(v if not isinstance(v,(dict,list)) else type(v).__name__+str(len(v))) for k,v in d.items()})[:300])" 2>&1)"
echo "calib: $(head -c 300 $N/state/mind/calibration.json | tr '\n' ' ')"
echo "weekly_exam ECE: $(grep -c -i ece $N/mods/weekly_exam.py)"; ls $N/mods | head -40 | tr '\n' ' '; echo
echo "advisor1 code in live chat_core: $(grep -n '_flag_on("chat_advisor1")' $N/web/pkg/server/chat_core.py | wc -l)"
echo END
