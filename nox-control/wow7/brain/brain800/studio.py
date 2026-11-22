"""Versioned, reversible edits to ten independent tracks of a NOX scene."""
from copy import deepcopy
from functools import partial

TRACKS = dict(voice="реплики", pause="паузы", cue="сигналы", caption="субтитры",
              focus="фокус", motion="движения", sound="звуки", color="цвета",
              shot="планы", note="заметки")
ACTIONS = dict(diff="сравнить две версии", merge="объединить независимые правки",
               take="перенести выбранные элементы", restore="вернуть элементы из базы",
               reorder="переставить элементы", trim="вырезать временное окно",
               shift="сдвинуть выбранные элементы во времени", overlay="найти наложения",
               at="выбрать активные элементы", duration="посчитать занятое время")

def read(scene, track):
    if not isinstance(scene, dict) or track not in scene:
        raise ValueError("Нет дорожки " + track)
    rows = scene[track]
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("Дорожка должна содержать до 256 элементов")
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            raise ValueError("Каждому элементу нужен уникальный строковый id")
        ids.add(row["id"])
        a,b = row.get("start"), row.get("end")
        if not all(type(x) is int for x in (a,b)) or not 0 <= a <= b:
            raise ValueError("start и end задаются в целых миллисекундах")
    return rows

def run(track, action, p):
    scene = p["scene"]
    rows = read(scene, track)
    left = {r["id"]:r for r in rows}
    if action in ("diff","merge","take","restore"):
        other = read(p["base" if action == "restore" else "alternate"], track)
        right = {r["id"]:r for r in other}
    if action == "diff":
        return {"added":[i for i in right if i not in left],
                "removed":[i for i in left if i not in right],
                "changed":[i for i in left if i in right and left[i] != right[i]],
                "order_changed":[i for i in left if i in right] != [i for i in right if i in left]}
    if action == "merge":
        base = {r["id"]:r for r in read(p["base"],track)}
        conflicts = []
        combined = []
        for i in dict.fromkeys([*left,*right,*base]):
            a,b,c = left.get(i),right.get(i),base.get(i)
            if a != b and a != c and b != c:
                conflicts.append(i)
            chosen = b if a == c else a
            if chosen is not None:
                combined.append(chosen)
        # Explicitly preserve the current ordering while importing alternate-only items.
        return {"scene":{**scene,track:combined},"unresolved":conflicts,"order_policy":"current_then_new"}
    if action in ("take","restore","shift","reorder"):
        chosen = p["ids"]
        if not isinstance(chosen,list) or not all(isinstance(x,str) for x in chosen) or len(set(chosen))!=len(chosen):
            raise ValueError("ids должен быть списком без повторов")
    if action in ("take","restore"):
        if set(chosen)-set(left)-set(right): raise ValueError("Неизвестный id")
        new = dict(left)
        for i in chosen:
            if i in right: new[i] = right[i]
            else: new.pop(i,None)
        changed = list(new.values())
    elif action == "reorder":
        if set(chosen) != set(left): raise ValueError("Требуются все id дорожки")
        changed = [left[i] for i in chosen]
    elif action == "shift":
        delta = p["ms"]
        if type(delta) is not int or set(chosen)-set(left): raise ValueError("Некорректный сдвиг или id")
        changed = [dict(r,start=r["start"]+delta,end=r["end"]+delta) if r["id"] in chosen else r for r in rows]
        if any(r["start"]<0 for r in changed):raise ValueError("Сдвиг выходит за начало сцены")
    elif action == "trim":
        start,end = p["window"]
        if type(start) is not int or type(end) is not int or not 0<=start<end:raise ValueError("Некорректное окно")
        changed = [dict(r,start=max(start,r["start"])-start,end=min(end,r["end"])-start)
                   for r in rows if max(start,r["start"])<min(end,r["end"])]
    elif action == "overlay":
        return [[r["id"],s["id"]] for j,r in enumerate(rows) for s in rows[j+1:]
                if max(r["start"],s["start"]) < min(r["end"],s["end"])]
    elif action == "at":
        return [r["id"] for r in rows if r["start"]<=p["ms"]<r["end"]]
    elif action == "duration":
        total = last = 0
        for r in sorted(rows,key=lambda r:r["start"]):
            total += max(0,r["end"]-max(last,r["start"]))
            last = max(last,r["end"])
        return {"occupied_ms":total,"span_ms":max((r["end"] for r in rows),default=0)-min((r["start"] for r in rows),default=0)}
    return {**scene,track:deepcopy(changed)}

OPS = {f"{t}.{a}":partial(run,t,a) for t in TRACKS for a in ACTIONS}
META = {f"{t}.{a}":f"{name.capitalize()} • {desc}" for t,name in TRACKS.items() for a,desc in ACTIONS.items()}
SAMPLE = {"scene":{},"base":{},"alternate":{},"ids":["b","a"],"ms":300,"window":[200,700]}
for t in TRACKS:
    start = [{"id":"a","start":0,"end":400,"value":"A"},{"id":"b","start":200,"end":900,"value":"B"}]
    SAMPLE["base"][t] = start
    SAMPLE["scene"][t] = [dict(start[0],value="Left"), start[1]]
    SAMPLE["alternate"][t] = [start[0],dict(start[1],value="Right")]
