echo "K1: full_chk1"
# Полная проверка: только числа и коды.
N=/workspace/nox; S=$N/web/site
echo "== services"
for p in nox_sidecar nox_voice nox_inspector nox_weekly_exam nox_sensorium_ext nox_mem; do echo "sv $p $(supervisorctl status $p 2>/dev/null | awk '{print $2}')"; done
for n_u in "llama8104 http://127.0.0.1:8104/health" "judge8300 http://127.0.0.1:8300/health" "gw8793 http://127.0.0.1:8793/health/liveliness" "mem18220 http://127.0.0.1:18220/health" "stt8093 http://127.0.0.1:8093/health" "voice18797 http://127.0.0.1:18797/health" "side18798 http://127.0.0.1:18798/health" "searx http://127.0.0.1:8888/healthz" "img http://127.0.0.1:18091/img/health" "music http://127.0.0.1:18091/music/gen"; do set -- $n_u; echo "svc $1 $(curl -s -o /dev/null -m 6 -w %{http_code} $2)"; done
echo "== pages"
bad=0; for p in chat-dc chat widgets music cinema photo voice training scene assistant board memory constructor finance news calendar atlas pdf projects writer/index coder/index designer/index; do c=$(curl -s -o /dev/null -m 8 -w %{http_code} http://127.0.0.1:18091/web/$p.html); [ "$c" = 200 ] || bad=$((bad+1)); printf "%s=%s " $p $c; done; echo; echo "pages_bad=$bad"
# assets referenced by pages exist
miss=0; for p in widgets music cinema photo voice training scene assistant board memory constructor finance news calendar atlas pdf projects chat-dc; do for a in $(grep -oE '/web/[A-Za-z0-9_./-]+\.(js|css)' $S/$p.html | sort -u); do c=$(curl -s -o /dev/null -m 6 -w %{http_code} http://127.0.0.1:18091$a); [ "$c" = 200 ] || { miss=$((miss+1)); echo "miss $p $a $c"; }; done; done; echo "assets_missing=$miss"
echo "== gate"; echo "gate $(curl -s -o /dev/null -m 8 -w %{http_code} -u owner:$(cat $N/state/owner_gate/pass) http://127.0.0.1:18092/web/chat-dc.html) noauth $(curl -s -o /dev/null -m 8 -w %{http_code} http://127.0.0.1:18092/web/chat-dc.html)"
echo "tunnel_proc=$(pgrep -fc 'cloudflared.*20999')"
echo "== gpu/disk"
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader
df -BG /workspace | awk 'NR==2{print "disk_free",$4}'
echo "== repeat/judge logs"
echo "repeat: $(grep -oE 'caught_[a-z]+|regenerated|living_reply_dropped' $N/state/chat_repeat.log 2>/dev/null | sort | uniq -c | tr '\n' ' ')"
echo "judge_lines=$(wc -l < $N/state/chat_judge.log 2>/dev/null) adv_lines=$(wc -l < $N/state/chat_advisors.log 2>/dev/null) inspector_hints=$(ls $N/state/inspector/hints 2>/dev/null | wc -l)"
echo "== training"
curl -s -m 6 http://127.0.0.1:18091/api/nox/training/status | python3 -c "import json,sys;o=json.load(sys.stdin);print('train',o.get('status'),o.get('phase'),'step',o.get('step'),'round',o.get('round'),'verdict',o.get('verdict'))" 2>/dev/null
echo "== chat quality"
python3 - <<'PY'
import json,time,urllib.request,uuid,hashlib
T=["Привет! Как ты?","Кто я для тебя?","Сколько будет 48*25-200?","Мне грустно сегодня.","Напиши хайку про осень.","Ты просто нейросеть?","Найди, что такое llama.cpp","Объясни DNS в двух предложениях.","Что ты помнишь о нашем разговоре?","Придумай три названия для кафе."]
cid="qa-full-"+uuid.uuid4().hex[:5]; shas=set(); tt=[]; bad=0
for q in T:
    t0=time.time();first=None;txt=[];end=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            s=ln.strip()
            if not s: continue
            o=json.loads(s); t=o.get("t")
            if t=="delta":
                txt.append(o.get("text") or "")
                if first is None: first=time.time()-t0
            if t in("done","error"): end=t; break
    except Exception as e: end=type(e).__name__
    a="".join(txt); shas.add(hashlib.sha1(a.encode()).hexdigest()); tt.append(first or 99)
    if end!="done" or not a: bad+=1
    print("Q ttft=%.2f total=%.1f end=%s len=%d calc=%d"%(first or 99,time.time()-t0,end,len(a),int("1000" in a)))
tt.sort(); print("CHAT distinct=%d/%d bad=%d med_ttft=%.2f max_ttft=%.2f"%(len(shas),len(T),bad,tt[len(tt)//2],tt[-1]))
PY
echo END
