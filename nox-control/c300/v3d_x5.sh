echo "K1: v3d_x5"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v3d5_$cb; mkdir -p $T
cp -a $S/v1n $T/v1n; cp -a $S/v2 $T/v2; for p in memory assistant board scene chat-dc; do [ -f $S/$p.html ] && cp -a $S/$p.html $T/; done
W=/tmp/v3d_$cb; mkdir -p $W; curl -fsSL "$R/v3d.list?cb=$cb" -o $W/list || { echo NOLIST; exit 0; }
n=0; bad=0; while read f; do mkdir -p $W/$(dirname "$f"); curl -fsSL --retry 4 "$R/v3d/$f?cb=$cb" -o "$W/$f" && n=$((n+1)) || { bad=$((bad+1)); echo "dlfail $f"; }; done < $W/list
echo "downloaded=$n bad=$bad"; [ $bad = 0 ] || { echo ABORT; exit 0; }
rm -rf $S/v1n; cp -r $W/v1n $S/v1n; cp -r $W/v2/* $S/v2/; cp $W/root/*.html $S/; echo "installed backup=$T"
for u in chat-dc.html v1n/ab.js memory.html constructor.html v2/memory.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo END
python3 - <<'PY'
import json,urllib.request
def j(u,b=None):
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091"+u,json.dumps(b).encode() if b else None,{"Content-Type":"application/json"}),timeout=20); return r.status,r.read()
    except urllib.error.HTTPError as e: return e.code,b""
    except Exception as e: return type(e).__name__,b""
c,b=j("/api/memory/graph?user=owner&n=200"); 
try: o=json.loads(b); print("graph",c,"ok",o.get("ok"),"nodes",len((o.get("elements") or {}).get("nodes") or []))
except Exception: print("graph",c)
c,b=j("/api/convs?user=owner"); 
try: print("convs",c,"n",len(json.loads(b)))
except Exception: print("convs",c)
c,b=j("/api/draft",{"conversation_id":"qa-d","prefix":"Сегодня я хочу"}); 
try: o=json.loads(b); print("draft",c,"ok",o.get("ok"),"len",len(o.get("draft") or ""))
except Exception: print("draft",c)
PY
echo END2
