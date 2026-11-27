echo "K1: dz_draw_probe2"
W=/workspace/nox/web/pkg/server
echo "--- _img_generate"; grep -n "def _img_generate" -A 40 $W/web_server.py | cut -c1-230 | head -70
echo "--- _c300_img_file"; grep -n "def _c300_img_file" -A 14 $W/web_server.py | cut -c1-200 | head -24
echo "--- live /img/generate"; t0=$(date +%s)
curl -s -m 60 -X POST http://127.0.0.1:18091/img/generate -H 'Content-Type: application/json' -d '{"prompt":"red circle on white background, simple","width":512,"height":512}' | python3 -c '
import sys,json
d=sys.stdin.read()
try:
    j=json.loads(d)
    print({k:(v[:80]+"..(%d)"%len(v) if isinstance(v,str) and len(v)>80 else v) for k,v in j.items()})
except Exception: print("nonjson",len(d),d[:200])'
echo "elapsed $(( $(date +%s)-t0 ))s"; curl -s -m 5 http://127.0.0.1:18091/img/health | head -c 300; echo
