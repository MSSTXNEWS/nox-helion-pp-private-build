import re, time, shutil, subprocess, os
ts = time.strftime("%Y%m%d%H%M%S"); out = []
def bak(p): shutil.copy(p, p + ".bak_" + ts)
# 1) boot_s1.sh: перезагрузка не должна откатывать настройки
p = "/root/nox/boot_s1.sh"; s = open(p).read(); bak(p)
s = re.sub(r'(\n\s*)nohup setsid \$BIN -m \$M --host 127\.0\.0\.1 --port 8081[^\n]*', r'\1bash /root/nox/start_glm.sh', s)
s = s.replace('grep -q "^NOX_UPSTREAM=http://127.0.0.1:$GLMP$"', 'grep -q "^NOX_UPSTREAM=http://127.0.0.1:8099$"')
s = s.replace('PYTHONPATH=$C NOX_UPSTREAM=http://127.0.0.1:$GLMP ', 'PYTHONPATH=$C NOX_UPSTREAM=http://127.0.0.1:8099 NOX_CONNECT_TIMEOUT=90 NOX_FAST_TIMEOUT=120 NOX_EMBED_URL= ')
s = s.replace('быстрый ответ — Qwen3.5-9B; глубокий — GLM-5.3 (отвечает только когда загружен)', 'быстрый ответ — Qwen3-30B-A3B; глубокий — GLM-5.3-Flash (режим «Глубоко»)')
s = re.sub(r'\{ cp \$C/s1web/web_server\.py \$N/web_server\.py;', '{ [ -f $N/web_server.py ] || cp $C/s1web/web_server.py $N/web_server.py;', s)
open(p, "w").write(s)
out.append("boot: start_glm=%d up8099=%d model=%d webkeep=%d" % (s.count("bash /root/nox/start_glm.sh"), s.count("NOX_UPSTREAM=http://127.0.0.1:8099"), s.count("GLM-5.3-Flash"), s.count("[ -f $N/web_server.py ]")))
# 2) web_server: занятость GLM по /slots (4 слота) + подпись
p = "/root/nox/web_server.py"; s = open(p).read(); bak(p)
old = 'c = http.client.HTTPConnection("127.0.0.1", 8081, timeout=2); c.request("GET", "/health"); d["glm_busy"] = c.getresponse().status == 503'
new = 'c = http.client.HTTPConnection("127.0.0.1", 8081, timeout=2); c.request("GET", "/slots"); d["glm_busy"] = any(x.get("is_processing") for x in json.loads(c.getresponse().read() or b"[]"))'
n1 = s.count(old); s = s.replace(old, new)
s = re.sub(r'GLM-5\.3(?!-Flash)', 'GLM-5.3-Flash', s)
open(p, "w").write(s); out.append("web busy patch=%d" % n1)
r = subprocess.run(["python3", "-m", "py_compile", p], capture_output=True, text=True); out.append("web compile rc=%d %s" % (r.returncode, r.stderr[-200:]))
if r.returncode: shutil.copy(p + ".bak_" + ts, p); out.append("web REVERTED")
# 3) фронт: жёлтая точка «занята» + имя модели
W = "/root/nox/web/"
for f in ("nox_mode.js", "nox-nav.js", "nox-newchat.js", "nox-wow.js"):
    p = W + f; s = open(p).read(); bak(p)
    s = re.sub(r'GLM-5\.3(?!-Flash)', 'GLM-5.3-Flash', s)
    if f == "nox_mode.js":
        s = s.replace("dot(s.glm_up)+'Глубокий · GLM-5.3-Flash (~1,4 ток/с)'", "(s.glm_busy?'<span class=\"dot\" style=\"background:#facc15\"></span>':dot(s.glm_up))+'Глубокий · GLM-5.3-Flash (~2,6 ток/с'+(s.glm_busy?', думает':'')+')'")
        out.append("widget busy=%d" % s.count("s.glm_busy?"))
    open(p, "w").write(s)
    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
    if r.returncode not in (0,) and "not found" not in r.stderr: 
        if os.path.exists("/usr/bin/node") or shutil.which("node"): shutil.copy(p + ".bak_" + ts, p); out.append(f + " REVERTED " + r.stderr[-150:])
h = W + "chat.html"; s = open(h).read(); bak(h); s = re.sub(r'(nox_mode\.js\?v=)\d+', r'\g<1>' + str(int(time.time())), s); open(h, "w").write(s)
print("\n".join(out))
