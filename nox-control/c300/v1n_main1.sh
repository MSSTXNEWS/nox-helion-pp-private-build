echo "K1: v1n_main1"
S=/workspace/nox/web/site; cb=$(date +%s)
[ -f $S/v1n/index.html ] || { echo NO_V1N; exit 0; }
cp -a $S/chat-dc.html /workspace/nox/state/web_bak_chatdc_$cb.html; cp -a $S/chat-dc.html $S/chat-dc-old.html
sed -e 's#"\.\./#"#g' -e "s#'\.\./#'#g" -e 's#"\./\(ab\.\(js\|css\)\)#"v1n/\1#g' -e 's#"\./fonts/#"v1n/fonts/#g' $S/v1n/index.html > /tmp/cdc_$cb.html
grep -q 'v1n/ab.js' /tmp/cdc_$cb.html && grep -q 'v1n/ab.css' /tmp/cdc_$cb.html || { echo BAD_REWRITE; exit 0; }
cp /tmp/cdc_$cb.html $S/chat-dc.html; echo "main=v1n backup=web_bak_chatdc_$cb old=chat-dc-old.html"
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") 2>/dev/null | tail -1
for u in chat-dc.html chat-dc-old.html v1n/ab.js v1n/ab.css; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo "dc_has_v1n=$(curl -s http://127.0.0.1:18091/web/chat-dc.html | grep -c 'v1n/ab.js')"
for f in nox-shell.js nox-nav.js; do [ -f $S/$f ] && echo "navref $f resonance_links=$(grep -o 'chat[a-z0-9-]*\.html' $S/$f | sort | uniq -c | tr '\n' ' ')"; done
python3 - <<'PY'
import json,time,urllib.request,uuid,threading
def live():
    try:o=json.loads(urllib.request.urlopen("http://127.0.0.1:18091/api/nox-live",timeout=4).read());c=o.get("chat_priority") or {};return c.get("paused"),o.get("live_turn")
    except Exception as e:return "err",None
print("IDLE prio_paused,live_turn",live(),"load",open("/proc/loadavg").read().split()[0])
for q in ["Сколько будет 17*23?","Объясни коротко, что такое DNS","Придумай слоган для кофейни"]:
    samples=[];stop=[0]
    def mon():
        while not stop[0]: samples.append((live(),open("/proc/loadavg").read().split()[0])); time.sleep(1)
    th=threading.Thread(target=mon);th.start();t0=time.time();first=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"rv-"+uuid.uuid4().hex[:6],"message":q,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            try:o=json.loads(ln)
            except Exception:continue
            k=o.get("t") or o.get("type")
            if k=="delta" and first is None:first=time.time()-t0
            if k in("done","error"):break
    except Exception as e:print("EXC",type(e).__name__)
    stop[0]=1;th.join()
    print("TURN ttft=%s total=%.1f paused_seen=%s load_max=%s"%(first and round(first,2),time.time()-t0,sorted({str(s[0][0]) for s in samples}),max(float(s[1]) for s in samples) if samples else None))
PY
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null | head -2
echo "trainer_procs=$(pgrep -fc 'dpo|char_cycle|train' )"
echo END
