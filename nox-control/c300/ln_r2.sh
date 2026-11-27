echo "K1: ln_r2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "== mem conf"; grep -A12 '\[program:nox_mem\]' /etc/supervisor/conf.d/*.conf 2>/dev/null | sed -E 's/(KEY|TOKEN|SECRET)[^,]*/\1=***/g' | head -20
supervisorctl tail nox_mem stderr 2>&1 | tail -8 | cut -c1-200
supervisorctl tail nox_mem 2>&1 | tail -4 | cut -c1-200
echo "== 18220"; curl -s -m5 -o /dev/null -w "%{http_code}\n" 127.0.0.1:18220/health
echo "== tunnel conf"; grep -A8 '\[program:nox_web_chat_tunnel\]' /etc/supervisor/conf.d/*.conf | sed -E 's#https?://[^ ]*#URL#g' | head -12
supervisorctl tail nox_web_chat_tunnel 2>&1 | tail -3 | sed -E 's#https?://[^ ]*#URL#g' | cut -c1-150
echo "== web files"; ls $N/web/pkg 2>/dev/null | head; find $N/web -maxdepth 3 -name '*.html' | head -80 | wc -l
echo "== which serves 8091"; ss -ltnp | grep -E ':8091 |:18091 ' | grep -oE 'users:\(\("[^"]+"' 
echo "== caddy routes"; ls /etc/caddy 2>/dev/null; 
echo "== listen ports full"; ss -ltn | awk 'NR>1{print $4}' | sed 's/.*://' | sort -n | tr '\n' ' ' | cut -c1-900
echo; echo "== disk guard log"; tail -3 $N/agent/out/disk_guard.log | cut -c1-160
echo "== soul_backup_ok"; head -c 300 $N/backup/soul_backup_ok.json; ls -la --time-style=+%H:%M $N/backup | tail -6
