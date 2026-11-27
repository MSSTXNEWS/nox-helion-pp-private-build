echo "K1: cx_lat1"
L=/workspace/nox/state/chat_fast.log
tail -n 120 $L | grep -oE "msgs=[0-9]+ chars=[0-9]+|первый токен [0-9.]+|slot=[0-9None]+ prompt_n=[0-9None]+ cache_n=[0-9None]+ prompt_ms=[0-9]+" | tail -60 | sed 's/первый токен/ftok/' | paste -sd' ' | sed 's/msgs=/\nmsgs=/g' | tail -25
echo "owner_active_writers: $(grep -rl 'owner_active' /workspace/nox --include=*.py --include=*.sh 2>/dev/null | head -12 | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
ls -la --time-style=+%H:%M /workspace/nox/state/owner_active 2>/dev/null | awk '{print "owner_active mtime",$6}'
python3 - <<'PY'
import json,urllib.request
try:
  d=json.loads(urllib.request.urlopen("http://127.0.0.1:8104/slots",timeout=2).read())
  print("SLOTS",[ (s.get("id"),int(bool(s.get("is_processing")))) for s in d])
except Exception as e: print("SLOTS err",type(e).__name__)
try:
  o=json.loads(urllib.request.urlopen("http://127.0.0.1:18091/api/nox/training/status",timeout=4).read()); g=o.get("generation_slots") or {}
  print("GEN active=%s servers=%s per_server=%s"%(g.get("active_generations"),g.get("servers_observed"),json.dumps(g.get("per_server"))[:300]))
except Exception as e: print("GEN err",type(e).__name__)
PY
echo END
