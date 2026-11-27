echo "K1: v1n_x3"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/v1n; cb=$(date +%s)
S=/workspace/nox/web/site; D=$S/v1n; [ -d $D ] && cp -a $D /workspace/nox/state/web_bak_v1n_$cb
W=/tmp/v1n_$cb; mkdir -p $W/fonts; ok=0
for k in 1 2 3 4 5 6; do fail=0
 for f in ab.css ab.js chat-dc.html chunk-5LOZM3L2.js chunk-AL54HLTZ.js chunk-BR5QOH6F.js chunk-E4H6O5CM.js chunk-EN73LCNK.js chunk-K5SORV3E.js chunk-NBK5OUN4.js chunk-OVPL2TEC.js chunk-RDEQJVVW.js chunk-SUKR6HHO.js chunk-TKQ4T5UH.js chunk-WV5VEHA4.js chunk-YAKSUMY3.js fonts/inter-cyrillic-wght-normal.woff2 fonts/inter-latin-wght-normal.woff2 fonts/jetbrains-mono-cyrillic-wght-normal.woff2 fonts/jetbrains-mono-latin-wght-normal.woff2 index.html; do curl -fsSL "$R/$f?cb=$cb$k" -o $W/$f || { fail=1; echo "dlfail $f"; }; done
 [ $fail = 0 ] && [ "$(sha256sum $W/ab.js | cut -c1-16)" = 0ffb9658e723c418 ] && { ok=1; break; }; sleep 5; done
[ $ok = 1 ] || { echo "STALE sha=$(sha256sum $W/ab.js | cut -c1-16)"; exit 0; }
rm -rf $D; mkdir -p $D; cp -r $W/* $D/; cp -a $S/chat-dc.html /workspace/nox/state/web_bak_chatdc_x3_$cb.html; cp $W/chat-dc.html $S/chat-dc.html; echo "installed files=$(find $D -type f | wc -l)"
bash <(curl -fsSL "$R/../th_graphite/webroot_sync.sh?cb=$cb") 2>/dev/null | tail -1
for u in chat.html v1n/index.html v1n/ab.js v1n/ab.css v1n/fonts/inter-cyrillic-wght-normal.woff2 chat-dc.html; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
python3 - <<'PY'
import json,urllib.request
for p in ("api/nox-live","api/nox/status","api/nox/training/status"):
    try:
        o=json.loads(urllib.request.urlopen("http://127.0.0.1:18091/"+p,timeout=6).read())
        def ks(x,d=0):
            if isinstance(x,dict) and d<2: return {k:ks(v,d+1) for k,v in list(x.items())[:25]}
            return type(x).__name__
        print("SHAPE",p,json.dumps(ks(o))[:900])
    except Exception as e: print("SHAPE",p,"err",type(e).__name__)
PY
echo END
