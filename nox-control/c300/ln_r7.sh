echo "K1: ln_r7"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
G=$(dirname $(readlink -f /proc/$(ss -ltnp | grep ':18218 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cwd)); echo guard dir $G
grep -nE "do_(GET|POST)|path *==|p *==|\"/[a-z_/]+\"" $(readlink -f /proc/$(ss -ltnp | grep ':18218 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cwd)/guard_svc.py | head -14 | cut -c1-170
echo "== stt/tts"; grep -nE "path *==|\"/[a-z_/]+\"|def synth|speaker|voice" $N/c300_voice/voice/tts_server.py | head -14 | cut -c1-160
grep -nE "path *==|\"/[a-z_/]+\"" $N/c300_voice/voice/stt_server.py | head -8 | cut -c1-160
echo "== agents"; AD=$(readlink -f /proc/$(ss -ltnp | grep ':8810 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cwd); echo $AD
grep -nE "\"/[a-z_/]+\"" $AD/nox_agents.py | head -40 | cut -c1-150
echo "== tools gw/searx ports"; for n in nox_tools_gateway nox_searxng nox_stt; do grep -h "command\|SEARXNG_PORT\|port" /etc/supervisor/conf.d/$n.conf 2>/dev/null | head -3 | cut -c1-160; done
echo "== self_now keys"; curl -s 127.0.0.1:18091/api/nox/self_now | python3 -c "
import sys,json;d=json.load(sys.stdin)['data']
for k,v in d.items(): print(k,type(v).__name__,(len(v) if hasattr(v,'__len__') else v))"
