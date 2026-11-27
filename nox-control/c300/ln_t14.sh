echo "K1: ln_t14"
export RUNNER_TRACKING_ID=""
curl -s -m8 127.0.0.1:18091/api/nox/self_now | python3 -c "
import sys,json;d=json.load(sys.stdin)['data']['telemetry']
live=[k for k,v in d.items() if v not in (None,'',{})]; print('telemetry live',len(live),'of',len(d),'; null:',[k for k in d if k not in live])"
python3 -c "
import json;d=json.load(open('/workspace/nox/canon/sensorium.json'))
print(type(d).__name__, list(d.keys())[:12] if isinstance(d,dict) else len(d))
s=d.get('sensors') if isinstance(d,dict) else None
print('sensors',(len(s) if s else None))"
