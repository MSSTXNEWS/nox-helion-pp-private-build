S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; T=bak_fx_b12
for f in $S/nox-registry.js $P/web_server.py; do [ -f $f.$T ] || cp $f $f.$T; done
/workspace/nox/venv/bin/python - <<'PYEOF'
S='/workspace/nox/web/site'; P='/workspace/nox/web/pkg/server'
def rd(p): return open(p,encoding='utf-8').read()
def wr(p,t): open(p,'w',encoding='utf-8').write(t)
t=rd(S+'/nox-registry.js')
old="const ok = async (u) => { try { const r = await fetch(u, { method: 'HEAD', cache: 'no-store' }); return r.ok; } catch (e) { return false; } };"
new="""let _exP = null;
const ok = async (u) => { try { if (!_exP) { const fs = [...LIBS, ...ASSETS].map((x) => x.file); _exP = fetch('/api/files-exist?p=' + encodeURIComponent(fs.join('|')), { cache: 'no-store' }).then((r) => (r.ok ? r.json() : {})).catch(() => ({})); } const ex = await _exP, k = u.replace(/^\\.\\//, ''); return k in ex ? !!ex[k] : (await fetch(u, { method: 'HEAD', cache: 'no-store' })).ok; } catch (e) { return false; } };"""
if old in t: wr(S+'/nox-registry.js',t.replace(old,new,1)); print('registry ok')
else: print('MISS registry')
w=P+'/web_server.py'; t=rd(w)
if 'files-exist' not in t:
    anchor='        if p == "/api/status": return self._j(200,'
    add='''        if p == "/api/files-exist":
            import urllib.parse as _up, os as _o
            _root = _o.path.realpath(os.environ.get("NOX_WEB_ROOT", "/workspace/nox/web/site")); _res = {}
            for _f in (_up.parse_qs(qs.lstrip("?")).get("p", [""])[0].split("|"))[:300]:
                _fp = _o.path.realpath(_o.path.join(_root, _f.lstrip("./")))
                _res[_f.lstrip("./") if _f.startswith("./") else _f] = _fp.startswith(_root + "/") and _o.path.isfile(_fp)
            return self._j(200, _res)
'''
    assert anchor in t; wr(w,t.replace(anchor,add+anchor,1)); print('server files-exist')
PYEOF
/workspace/nox/venv/bin/python -m py_compile $P/web_server.py && echo COMPILE_OK && bash $P/run_web.sh restart 2>&1 | tail -2
sleep 3; curl -s -m6 "http://127.0.0.1:8091/api/files-exist?p=vendor/three/package.json%7Cvendor/nox-planets/nox-mars.jpg%7C../etc/passwd"; echo
sed -n 64,95p /workspace/nox/qa_ctl.py | cut -c1-200
python3 -c "
import json;r=json.load(open('$S/qa/report.json'));print(r['ts'],r['bad'],r['total'])"; date
