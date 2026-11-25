echo "C300: d_s0"
for r in glanceapp/glance usememos/memos henrygd/beszel coder/code-server Stirling-Tools/Stirling-PDF; do echo "== $r"; curl -sL -m 30 https://api.github.com/repos/$r/releases/latest | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('tag_name'));[print(a['browser_download_url'],a['size']//1048576) for a in d.get('assets',[]) if any(k in a['name'].lower() for k in ('linux_amd64','linux-amd64','linux-x64','amd64.tar','.jar')) and 'sha' not in a['name'].lower() and 'deb' not in a['name'] and 'rpm' not in a['name'] and 'apk' not in a['name']]" 2>&1 | head -12; done
java -version 2>&1 | head -1; ls /usr/lib/jvm 2>/dev/null
curl -sL -m 20 -o /dev/null -w "temurin %{http_code}\n" "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jre/hotspot/normal/eclipse"
sed -n 1,60p /workspace/nox/web/pkg/server/svc_proxy.py | cut -c1-160
grep -n "websocket\|upgrade\|Upgrade" /workspace/nox/web/pkg/server/svc_proxy.py | head -5
uv python list 2>/dev/null | head -5; ls /workspace/nox/svc/logs | head; ls /workspace/nox/venv/bin/python
ss -ltn | awk '{print $4}' | grep 127.0.0.1 | sort | tr '\n' ' '
