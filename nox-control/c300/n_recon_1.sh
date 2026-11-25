echo "C300: n_recon_1"
cd /workspace/nox
df -h /workspace | tail -1; free -m | sed -n 2p; nproc
python3 --version; ls /workspace/nox | head -50; ls venv_living 2>&1 | head -2
echo "== registry"; python3 - <<'P'
import json;r=json.load(open('/workspace/nox/web/pkg/server/svc_registry.json'));print(type(r).__name__,len(r))
print(json.dumps(r,ensure_ascii=False)[:1800])
P
echo "== start_extra"; tail -25 svc/start_extra.sh
echo "== ports"; (ss -ltnp 2>/dev/null || netstat -ltn) | awk '{print $4}' | sed 's/.*://' | sort -n | uniq | tr '\n' ' '
echo; echo "== persona"; python3 - <<'P'
import json;d=json.load(open('/workspace/nox/state/persona.json'));print(list(d.keys()))
P
ls state/living 2>&1 | head
echo "== chat_core"; wc -l web/pkg/server/chat_core.py; grep -n "^def \|^async def \|^class \|persona\|system_hint\|living" web/pkg/server/chat_core.py | head -70
echo "== net"; curl -sI -m 8 https://pypi.org | head -1; curl -sI -m 8 https://huggingface.co | head -1
echo "== pip"; python3 -m venv --help >/dev/null 2>&1 && echo venv_ok; pip --version
ls web/site/qa/rework 2>&1 | tail -3; ls nox-control 2>&1 | head -3
