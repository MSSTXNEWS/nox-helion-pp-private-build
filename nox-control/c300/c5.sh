S=/workspace/nox/svc
ps aux | grep -E "filebrowser|jellyfin" | grep -v grep | awk '{print $11,$12,$13,$14,$15}'
tail -3 $S/logs/jellyfin.log | cut -c1-200; ls -la $S/logs
curl -s -m5 -i localhost:8097/svc/filebrowser/ | head -5; curl -s -m5 -o /dev/null -w "root %{http_code}\n" localhost:8097/
$S/filebrowser/filebrowser config cat -d $S/data/filebrowser/fb.db | grep -i "base\|port\|auth\|root" 
curl -s -m10 -i localhost:8091/svc/freshrss/ | head -8
curl -s -m10 -i localhost:8098/ | head -6
curl -s -m10 -o /dev/null -w "jf %{http_code}\n" localhost:8096/svc/jellyfin/web/
