S=/workspace/nox/svc
sed -i 's/8097/8187/g' $S/start_all.sh
python3 - <<'P'
import json;p='/workspace/nox/web/pkg/server/svc_registry.json';d=json.load(open(p));d['filebrowser']['port']=8187;json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
P
$S/filebrowser/filebrowser config set -d $S/data/filebrowser/fb.db -p 8187 >/dev/null 2>&1
nohup setsid bash $S/start_all.sh >/dev/null 2>&1 &
sleep 8
for s in filebrowser navidrome jellyfin freshrss ntfy; do echo -n "$s "; curl -s -m 10 -o /dev/null -w "%{http_code} " localhost:8091/svc/$s/; done; echo
curl -s -m10 -i localhost:8096/svc/jellyfin/web/index.html | head -3
curl -s -m10 localhost:8091/svc/filebrowser/ | head -c 200; echo
curl -s -m10 -i localhost:8091/svc/navidrome/ | head -4
