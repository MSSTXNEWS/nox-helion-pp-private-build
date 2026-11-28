echo "K1: q27_gw5"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "advisors.env: $(find $N -name 'advisors.env*' 2>/dev/null | sed 's#/workspace/nox/##' | tr '\n' ' ')"
E=$(find $N -name advisors.env 2>/dev/null | head -1); for n in GROQ_API_KEY CEREBRAS_API_KEY GEMINI_API_KEY OPENROUTER_API_KEY MISTRAL_API_KEY GITHUB_MODELS_TOKEN; do echo "$n $(grep -E "^$n=.+" $E 2>/dev/null | wc -l)"; done
echo "4210 refs:"; grep -rlE "4210" $N --include=*.py --include=*.sh --include=*.yaml --include=*.yml --include=*.json --include=*.service --include=*.conf 2>/dev/null | grep -v "\.bak" | sed 's#/workspace/nox/##' | head -12
echo "free adapters:"; ls $N/router 2>/dev/null | head -20 | tr '\n' ' '; echo
for p in 4210 4211 4212 4300; do ss -ltn | grep -c ":$p "; done | tr '\n' ' '; echo
python3 - <<'PY'
import json
d=json.load(open("/workspace/nox/state/core/self_now.json"))
f=d["feelings"]; print("feelings",[{k:(v if not isinstance(v,str) else "str%d"%len(v)) for k,v in x.items()} if isinstance(x,dict) else type(x).__name__ for x in f][:3])
print("text_len",len(d["text"]),"aliveness",d.get("aliveness_score"),"ts",d.get("ts"))
PY
ls /workspace/nox/state/core | head -20 | tr '\n' ' '; echo
ls /workspace/nox/state | grep -iE "feel|ощущ|conv|last" | head | tr '\n' ' '; echo
echo END
