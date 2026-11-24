S=/workspace/nox/svc
grep -n "jellyfin" $S/start_all.sh | cut -c1-200
PID=$(ss -ltnp | grep ':8096 ' | sed 's/.*pid=\([0-9]*\).*/\1/'); echo pid $PID; tr '\0' ' ' < /proc/$PID/environ | grep -o "DOTNET_[A-Z_]*=[0-9]" ; kill $PID; sleep 3
nohup setsid bash $S/start_all.sh >/dev/null 2>&1 &
sleep 40
curl -s -m10 -o /dev/null -w "jf %{http_code}\n" localhost:8091/svc/jellyfin/web/index.html
curl -s -m10 localhost:8091/svc/jellyfin/System/Info/Public | head -c 300
tail -3 $S/logs/jellyfin.log | cut -c1-200
