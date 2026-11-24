import json, shutil, time, copy
p="/workspace/nox/web/site/nav.json"; shutil.copy(p, p+".bak_c300_"+time.strftime("%H%M%S")); d=json.load(open(p))
def has(o): return isinstance(o, dict) and any(isinstance(v, str) and "cinema.html" in v for v in o.values())
added=[]
def walk(o):
    if isinstance(o, list):
        for i, x in enumerate(list(o)):
            if has(x) and not any(isinstance(y, dict) and any(isinstance(v, str) and "tools.html" in v for v in y.values()) for y in o):
                for href, name, icon, idn in (("tools.html", "Инструменты", "tools", "tools"), ("tv.html", "Проектор", "device-tv", "tv")):
                    n = copy.deepcopy(x)
                    for k, v in list(n.items()):
                        if isinstance(v, str):
                            if "cinema.html" in v: n[k] = v.replace("cinema.html", href)
                            elif k in ("id", "page", "key"): n[k] = idn
                            elif k in ("icon", "ic"): n[k] = icon
                            elif k in ("t", "title", "label", "name", "n", "text"): n[k] = name
                            elif k in ("d", "desc", "hint", "sub"): n[k] = "20 модулей с NOX" if idn == "tools" else "ТВ-режим для Android TV"
                    o.insert(o.index(x) + 1 + len([a for a in added if a[0] is o]), n); added.append((o, href))
                break
        for x in o: walk(x)
    elif isinstance(o, dict):
        for v in o.values(): walk(v)
print("cinema entry:", json.dumps([x for x in (d if isinstance(d, list) else []) if has(x)][:1], ensure_ascii=False)[:300])
walk(d); json.dump(d, open(p, "w"), ensure_ascii=False, indent=1); print("added", [a[1] for a in added])
