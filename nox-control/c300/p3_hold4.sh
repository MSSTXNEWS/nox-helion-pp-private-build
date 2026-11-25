N=/workspace/nox
for i in 1 2 3 4; do
 echo "-- t$i chat_activity age=$(( $(date +%s) - $(stat -c %Y $N/state/core/chat_activity) ))s"
 ss -Htnp state established '( dport = :8090 or dport = :8084 )' | while read l; do pid=$(echo "$l" | grep -o 'pid=[0-9]*' | cut -d= -f2); dp=$(echo $l | awk '{print $4}'); echo "-> $dp pid=$pid age=$(ps -o etimes= -p $pid 2>/dev/null|tr -d ' ') $(tr '\0' ' ' </proc/$pid/cmdline 2>/dev/null | cut -c1-120)"; done
 sleep 6
done
echo "== fresh web_conv"; ls -lt --time-style=+%T $N/state/web/web_conv | head -8
echo "== conv ids/first msgs of newest"; for f in $(ls -t $N/state/web/web_conv/*.json | head -4); do python3 -c "
import json;d=json.load(open('$f'));m=d.get('messages',[]);print('$f'.split('/')[-1],len(m),[x.get('role')+':'+str(x.get('content'))[:60] for x in m[-2:]], [x.get('source') for x in m[-2:]])"; done
