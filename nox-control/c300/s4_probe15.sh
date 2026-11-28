N=/workspace/nox; mask(){ sed -E 's#https://[a-z0-9-]+\.trycloudflare\.com#https://***.trycloudflare.com#g'; }
echo "S4P15 $(date +%F_%H:%M)"
echo "## run_tunnel.sh"; cat $N/ops/web_chat_auth/run_tunnel.sh | mask | cut -c1-240 | head -40
echo "## conf rest"; sed -n 12,30p /etc/supervisor/conf.d/nox_web_chat_tunnel.conf
echo "## tunnel logs tail"; tail -n 8 $N/agent/out/web_chat_tunnel_supervisord.log | mask | cut -c1-240; echo ---; tail -n 6 $N/agent/out/web_chat_tunnel.log | mask | cut -c1-240
echo "## TUNNEL_URL files"; for f in $N/agent/out/TUNNEL_URL.txt $N/agent/out/API_TUNNEL_URL.txt; do echo "$f age_h=$(( ($(date +%s)-$(stat -c %Y $f))/3600 )) $(cat $f | mask | head -c 120)"; done
echo "## 8120 + cloudflared 84781"; ss -ltnp | grep ':8120 ' | awk '{print $4,$6}'; ps -o pid,etimes,args -p 84781 | tail -1 | cut -c1-200
echo "## who runs quick tunnels to 18092/18091"; ps -eo pid,args | grep -E "cloudflared|ssh .*-R|serveo|localhost.run" | grep -E "18091|18092|8091" | head
echo "## consumers of tunnel url"; grep -rIl --include=*.py --include=*.sh -e "TUNNEL_URL" -e "trycloudflare" $N/mods $N/ops $N/agent/nox_agents $N/web/pkg 2>/dev/null | head -8
echo "## owner-gate/caddy supervisor"; supervisorctl status nox_web_chat_auth nox_sidecar nox_voice caddy 2>&1 | cut -c1-100
echo "## health probes"; for u in http://127.0.0.1:18092/ http://127.0.0.1:18091/ http://127.0.0.1:18797/ http://127.0.0.1:8104/health http://127.0.0.1:8400/health; do echo "$u -> $(curl -s -m4 -o /dev/null -w '%{http_code} %{time_total}s' $u)"; done
echo "## sidecar port"; ss -ltnp | grep -E "pid=1686035" | awk '{print $4}'; grep -n -E "PORT|port" $N/mods/nox_sidecar.py | head -4 | cut -c1-160
echo "## weekly_exam item1 + morning brief"; grep -n -E "def .*(item1|p1|uptime)|uptime_h|\"1\"" $N/mods/weekly_exam.py | head -8 | cut -c1-200; ls $N/state/mind | grep -i brief | head
echo "## body_restart callers"; grep -n "body_restart" $N/ops/dpo/char_cycle.sh $N/agent/autotrain/autotrain.sh $N/agent/autotrain/*.sh 2>/dev/null | cut -c1-220 | head -20
