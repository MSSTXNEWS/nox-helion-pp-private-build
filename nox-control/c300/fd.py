import shutil, time, subprocess, re
p="/root/nox/web_server.py"; s=open(p).read(); shutil.copy(p,p+".bak_fd_"+time.strftime("%H%M%S"))
a='_tgt = GW; _deep = _mode in ("deep", "max") or os.environ.get("NOX_SMALL_OFF", "0") == "1"'
assert s.count(a)==1, "anchor1"
s=s.replace(a, a+'\n        _fdir = (not _deep) and os.environ.get("NOX_FAST_DIRECT", "1") == "1"  # c300: быстрый ответ напрямую в :8083 со своей душой и памятью, без ядра с телеметрией')
b='        if _deep:  # Глубоко'
assert s.count(b)==1, "anchor2"
s=s.replace(b,'        if _deep or _fdir:  # Глубоко / Быстро напрямую')
c='            _tgt = os.environ.get("NOX_DEEP_DIRECT", "127.0.0.1:8081")'
assert s.count(c)==1, "anchor3"
s=s.replace(c,'            _tgt = os.environ.get("NOX_DEEP_DIRECT", "127.0.0.1:8081") if _deep else os.environ.get("NOX_FAST_DIRECT_URL", "127.0.0.1:8083")')
d='"\\nТы — глубокий уровень NOX на модели GLM-5.3-Flash.'
if s.count(d)==1:
    s=s.replace('_soul += '+d, '_soul += ("\\nТы — глубокий уровень NOX на модели GLM-5.3-Flash." if _deep else "\\nТы — быстрый уровень NOX (Qwen3-30B): отвечай сразу.") + "')
e='            if _deep and ok and _user_text:'
if s.count(e)==1: s=s.replace(e,'            if (_deep or _fdir) and ok and _user_text:')
open(p,"w").write(s)
r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-300:])
if r.returncode: shutil.copy(sorted(__import__("glob").glob(p+".bak_fd_*"))[-1],p); print("REVERTED")
print("soul label", s.count("быстрый уровень NOX (Qwen3-30B)"))
