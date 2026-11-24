S=/workspace/nox/web/site
grep -n "probeAll" $S/nox-api.js | head -3
awk '/probeAll/{f=1} f{print substr($0,1,700)} /^}/{if(f)exit}' $S/nox-api.js | head -60
echo ==ST; grep -n "ST_RU\|export const call\|export async function call" $S/nox-api.js | cut -c1-300
echo ==memok; curl -s -m4 -i http://127.0.0.1:8091/memory/health | head -12; ss -ltn | grep -E "8095|8301"
curl -s -m4 http://127.0.0.1:8091/glm/v1/nox/stats | python3 -c "import sys,json;d=json.load(sys.stdin);print(list(d.keys()));print({k:(v if not isinstance(v,dict) else list(v)[:12]) for k,v in d.items() if k!='health'})"
