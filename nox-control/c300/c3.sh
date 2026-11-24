L=/workspace/nox/svc/logs
for f in jellyfin ntfy filebrowser freshrss; do echo "== $f"; grep -v "^\s*at " $L/$f.log | tail -6 | cut -c1-260; done
ps aux | grep -E "jellyfin|ntfy|filebrowser|navidrome|php -S" | grep -v grep | awk '{print $11,$12,$13}' | head
for p in 8097 2586 8096; do echo -n "$p "; (echo > /dev/tcp/127.0.0.1/$p) 2>&1 && echo open || echo closed; done
curl -s -m5 -o /dev/null -w "fb direct %{http_code}\n" localhost:8097/svc/filebrowser/
curl -s -m5 -w "\nntfy health %{http_code}\n" localhost:2586/v1/health
curl -s -m8 -o /dev/null -w "frss %{http_code} " localhost:8091/svc/freshrss/; curl -s -m8 localhost:8091/svc/freshrss/ | head -c 300
