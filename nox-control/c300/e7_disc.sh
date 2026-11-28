echo "K1: e7_disc (read-only)"; N=/workspace/nox; S=$N/state/core; M=$N/state/mind
echo "## img routes"; for f in $(find $N -name 'image_service.py' -not -path '*/archive/*' 2>/dev/null | head -2); do echo $f; grep -o -E '"/[a-zA-Z0-9_/\-]+"' $f | sort -u | tr '\n' ' '; echo; grep -n -E "ttft|def do_POST|Content-Type" $f | head -5; done
echo "## ports"; ss -ltn 2>/dev/null | awk '{print $4}' | grep -E ':(8400|8500|18091|8091|18220)$' | tr '\n' ' '; echo
echo "## inj sets"; find $N/state $N/ops $N/agent -maxdepth 4 \( -iname '*inj*' \) -not -path '*/archive/*' 2>/dev/null | head -12
echo "## calib"; ls -la $M/calibration* 2>/dev/null; head -c 400 $M/calibration.jsonl 2>/dev/null; echo
echo "## morning brief writers"; grep -rl "morning_brief_v5" $N/mods $N/agent $N/ops $N/web/pkg 2>/dev/null | head -5; ls $S | grep -i -E "brief|morning" | head
echo "## conv sample"; f=$(ls -t $N/state/web/web_conv/*.json | head -1); python3 -I - "$f" <<'PY'
import json,sys
c=json.load(open(sys.argv[1])); print(list(c.keys())); m=c.get("messages",[])[-1:]; print([{k:(type(v).__name__) for k,v in x.items()} for x in m]); print([x.get("ts") for x in c.get("messages",[])[-2:]])
PY
echo "## journal kinds"; python3 -I - <<'PY'
import json,collections
k=collections.Counter(); n=0
for l in open("/workspace/nox/state/core/journal.jsonl",encoding="utf-8"):
    try: k[json.loads(l).get("kind")]+=1
    except Exception: pass
print(dict(k.most_common(25)))
PY
echo "## self_now keys"; python3 -I -c "import json;d=json.load(open('$S/self_now.json'));print({k:type(v).__name__ for k,v in d.items()})"
echo "## passport name keys"; python3 -I -c "import json;d=json.load(open('$S/passport.json'));print([k for k in d if 'name' in k.lower() or 'имя' in k.lower()][:5], list(d)[:15])"
echo "## oom"; grep oom_kill /proc/vmstat; dmesg -T 2>/dev/null | tail -1 | cut -c1-60; echo "dmesg_rc=$?"
echo "## gate_log last"; tail -1 $N/state/p3/gate_log.jsonl | cut -c1-400
ls $N/state/gates 2>/dev/null | tail -3; ls $M | head -40; ls $S/modes* $M/mode* 2>/dev/null
echo "## voice"; grep -n "8400\|PORT" $N/mods/voice_service.py | head -3
echo END
