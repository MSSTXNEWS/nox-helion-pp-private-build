import json, re, time
P='/workspace/nox/web/pkg/server/nox_cmd.py'; R='/workspace/nox/web/site/qa/registry.json'; S='/workspace/nox/web/site/'
t=open(P,encoding='utf-8').read()
if '_b_persona_set' not in t:
    code='''

# ---- S3: ползунки личности -> /workspace/nox/state/persona.json (ядро читает файл? см. core_reads) ----
PERSONA_F = "/workspace/nox/state/persona.json"
PERSONA_KEYS = {"curiosity": "любопытство", "humor": "юмор", "strictness": "строгость", "initiative": "инициатива", "empathy": "эмпатия", "brevity": "краткость"}
def _persona_load():
    try:
        with open(PERSONA_F, encoding="utf-8") as f: d = json.load(f)
    except Exception: d = {}
    return {k: int(d.get(k, 50)) for k in PERSONA_KEYS}
def _persona_core_reads():
    import glob
    for fn in glob.glob("/workspace/nox/brain/BRAIN/*.py"):
        try:
            with open(fn, encoding="utf-8", errors="replace") as f:
                if "persona.json" in f.read(): return True
        except Exception: pass
    return False
def _persona_hint(v):
    lv = lambda x: "очень высокий" if x >= 80 else "высокий" if x >= 60 else "средний" if x > 40 else "низкий" if x > 20 else "минимальный"
    return "Черты характера (0-100): " + "; ".join("%s %d (%s)" % (PERSONA_KEYS[k], v[k], lv(v[k])) for k in PERSONA_KEYS) + "."
def _b_persona_get(p):
    v = _persona_load()
    return 200, {"ok": True, "result": json.dumps({"values": v, "core_reads": _persona_core_reads()}, ensure_ascii=False)}
def _b_persona_set(p):
    v = _persona_load()
    for k in PERSONA_KEYS:
        if k in p:
            try: x = int(p[k])
            except Exception: return 400, {"ok": False, "error": k + ": нужно целое 0-100"}
            if not 0 <= x <= 100: return 400, {"ok": False, "error": k + ": вне диапазона 0-100"}
            v[k] = x
    out = dict(v); out["system_hint"] = _persona_hint(v); out["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp = PERSONA_F + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PERSONA_F)
    return 200, {"ok": True, "result": json.dumps({"values": v, "core_reads": _persona_core_reads()}, ensure_ascii=False)}
BUILTIN["persona.set"] = _b_persona_set
BUILTIN["persona.get"] = _b_persona_get
'''
    if 'import os' not in t.split('\n\n')[0] and not re.search(r'^import .*\bos\b|^import os', t, re.M): t = 'import os\n' + t
    t=t+code; open(P,'w',encoding='utf-8').write(t)
r=json.load(open(R,encoding='utf-8'))
props={k:{'type':'integer','minimum':0,'maximum':100,'description':v} for k,v in {'curiosity':'любопытство','humor':'юмор','strictness':'строгость','initiative':'инициатива','empathy':'эмпатия','brevity':'краткость'}.items()}
r['commands']['persona.set']={'desc':'Сохранить ползунки личности (любопытство, юмор, строгость, инициатива, эмпатия, краткость)','method':'POST','endpoint':None,'builtin':'persona.set','params':{'type':'object','properties':props},'confirm':False,'aliases':['личность','характер','ползунки личности']}
r['commands']['persona.get']={'desc':'Прочитать ползунки личности','method':'POST','endpoint':None,'builtin':'persona.get','params':{'type':'object','properties':{}},'confirm':False}
json.dump(r,open(R,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
# nav-x: хлебная крошка без дубля «МУЗЫКА / МУЗЫКА»
f=S+'nox-nav-x.js'; s=open(f,encoding='utf-8').read()
old="el.innerHTML = '<b>' + esc(nm(g.group)) + '</b> / ' + esc(nm(it.title));"
new="{ const a = nm(g.group), b = nm(it.title); el.innerHTML = (String(a).trim().toLowerCase() === String(b).trim().toLowerCase()) ? '<b>' + esc(a) + '</b>' : '<b>' + esc(a) + '</b> / ' + esc(b); }"
if old in s: open(f,'w',encoding='utf-8').write(s.replace(old,new)); print('crumb patched')
else: print('crumb pattern NOT found')
# settings tab: панель личности
f=S+'nox-settings-tabs.js'; s=open(f,encoding='utf-8').read()
if 'nxsPersona' not in s:
    s2=re.sub(r'<p class="note">Ползунки характера.*?Характер и ценности','<div id="nxsPersona" class="nxs-persona"></div><p class="note">Характер и ценности',s,count=1,flags=re.S)
    print('tabs patched' if s2!=s else 'tabs pattern NOT found')
    s2+="\n;(function(){var s=document.createElement('script');s.src='./nox-persona.js';document.head.appendChild(s)})();\n"
    open(f,'w',encoding='utf-8').write(s2)
# nav.json: Glance в ВИДЖЕТЫ
f=S+'nav.json'; n=json.load(open(f,encoding='utf-8'))
g=[x for x in n['groups'] if x['group']=='ВИДЖЕТЫ'][0]
if not any(i['file']=='glance.html' for i in g['items']):
    g['items'].append({'file':'glance.html','name':'Лента','title':'NOX HELION · ЛЕНТА','icon':'layout-board','desc':'Glance: погода, новости, рынки','soon':False})
    pg=n.get('pages')
    if isinstance(pg,list) and 'about.html' in pg: pg.append('glance.html')
    elif isinstance(pg,dict) and 'about.html' in pg: pg['glance.html']=pg['about.html']
    json.dump(n,open(f,'w',encoding='utf-8'),ensure_ascii=False,indent=1); print('nav glance added', type(pg).__name__)
# svc_registry: glance за прокси со срезом префикса
f='/workspace/nox/web/pkg/server/svc_registry.json'; d=json.load(open(f,encoding='utf-8'))
if d['glance'].get('mode')!='strip': d['glance']['mode']='strip'; json.dump(d,open(f,'w',encoding='utf-8'),ensure_ascii=False,indent=2); print('glance mode strip')
