echo "== F1"
for p in 8081 8082 8083 8090 8091 8099; do echo -n "$p="; curl -s -m4 -o /dev/null -w "%{http_code} " http://127.0.0.1:$p/health; done; echo
pgrep -af "llama-server|:8099|8099|proxy" | grep -v pgrep | cut -c1-330
grep -n "FAILED" -B4 /root/nox/logs/flash.log | cut -c1-160 | tail -8
for m in fast deep; do for q in "привет" "Объясни в двух предложениях, что такое RAID."; do
echo "-- $m: $q"; curl -s -m150 localhost:8082/v1/chat/completions -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$q\"}],\"nox_mode\":\"$m\",\"max_tokens\":300}" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin);c=d["choices"][0]["message"];print("len",len(c.get("content") or ""),"reas",len(c.get("reasoning_content") or ""),(d.get("nox") or {}).get("path"))
except Exception as e: print("ERR",e)'; done; done
