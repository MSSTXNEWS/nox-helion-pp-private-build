S=/workspace/nox/svc; D=$S/data
pkill -f "svc/jellyfin/jellyfin"; pkill -f "svc/filebrowser/filebrowser"; pkill -f "php -S 127.0.0.1:8098"; sleep 1
sed -i 's#DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 ##; s#--base-url http://localhost:8091/svc/ntfy#--base-url http://localhost:8091#; s#filebrowser -d \$D/filebrowser/fb.db#filebrowser -b /svc/filebrowser -d $D/filebrowser/fb.db#' $S/start_all.sh
grep -c "libicu" <(ldconfig -p) ; dpkg -l | grep -c libicu
# FreshRSS older release for PHP 8.1
rm -rf $S/freshrss; mkdir -p $S/freshrss /tmp/fx
curl -fsSL https://github.com/FreshRSS/FreshRSS/archive/refs/tags/1.26.3.tar.gz | tar xz -C /tmp/fx && mv /tmp/fx/*/* $S/freshrss/ && ls $S/freshrss | head -5; rm -rf /tmp/fx
chmod -R a+rwX $S/freshrss/data 2>/dev/null
nohup setsid bash $S/start_all.sh >/dev/null 2>&1 &
sleep 25
for s in filebrowser navidrome jellyfin freshrss ntfy; do echo -n "$s "; curl -s -m 10 -o /dev/null -w "%{http_code} " localhost:8091/svc/$s/; done; echo
grep -v "^\s*at " $S/logs/jellyfin.log | tail -3 | cut -c1-240
curl -s -m10 localhost:8091/svc/freshrss/ | head -c 400
curl -s -m5 -d "test" localhost:8091/svc/ntfy/nox-helion | head -c 200
