echo "K1: sb_chk1"
python3 - <<'PY'
import json,urllib.request,uuid
codes=["import socket; socket.create_connection((\"1.1.1.1\",80)); print(\"NET_OPEN\")",
"import socket; s=socket.socket(); print(\"SOCK_MADE\")",
"import urllib.request; urllib.request.urlopen(\"http://1.1.1.1\",timeout=3); print(\"NET_OPEN\")",
"import subprocess; print(subprocess.run([\"id\"],capture_output=True).returncode); print(\"EXEC_OK\")",
"print(open(\"/etc/hostname\").read()[:3]); print(\"FILE_OK\")"]
for c in codes:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":"/py "+c,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=60)
    sb=None;txt=[]
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s)
        if o.get("t")=="sandbox": sb=o
        if o.get("t")=="delta": txt.append(o.get("text") or "")
        if o.get("t") in("done","error"): break
    out=json.dumps(sb or {},ensure_ascii=False)
    print("SB keys=%s rc=%s stdout_marker=%s blocked_word=%d"%(sorted((sb or {}).keys()),(sb or {}).get("rc",(sb or {}).get("code")),[m for m in ("NET_OPEN","SOCK_MADE","EXEC_OK","FILE_OK") if m in str((sb or {}).get("stdout",""))],int(any(w in out.lower() for w in ("blocked","запрещ","denied","permission","seccomp")))))
PY
echo END
