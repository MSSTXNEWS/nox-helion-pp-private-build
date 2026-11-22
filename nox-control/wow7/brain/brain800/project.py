"""Local project operations for NOX. Data-only API. Dates are ISO calendar dates, effort in hours.

A payload has tasks (an array of task records with unique id, dependencies in deps),
and optional today, capacities (hours/day by owner), baseline (previous task array),
and decisions (array). Focused operations accept task_id and operation-specific fields.
Updates return replacement tasks or decisions; the caller controls persistence.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
from functools import partial
from graphlib import TopologicalSorter, CycleError
from math import ceil, isfinite
from statistics import median


OPS = {}
META = {}


def operation(key, description):
    def register(fn):
        OPS[key] = fn
        META[key] = description
        return fn
    return register


def records(p, field="tasks"):
    items = p.get(field, [])
    if not isinstance(items, list):
        raise ValueError(f"{field}: expected array")
    indexed = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError(f"{field}: each record needs a nonempty string id")
        if item["id"] in indexed:
            raise ValueError(f"{field}: duplicate {item['id']}")
        indexed[item["id"]] = item
    return indexed


def deps(task):
    values = task.get("deps", [])
    if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
        raise ValueError("deps: expected array of ids")
    return set(values)


def focus(p):
    idx = records(p)
    k = p.get("task_id")
    if k not in idx:
        raise ValueError("unknown task_id")
    return idx[k]


def number(v):
    n = float(v)
    if not isfinite(n) or n < 0:
        raise ValueError("expected a finite nonnegative quantity")
    return n


def hours(t):
    return number(t.get("estimate", 0))


def spent(t):
    return number(t.get("spent", 0))


def remaining(t):
    return 0 if t.get("status") == "done" else max(0, hours(t)-spent(t))


def day(s):
    return date.fromisoformat(s)


def current(p):
    return day(p["today"])


def open_items(p):
    return [t for t in records(p).values() if t.get("status") != "done"]


def owner(t):
    return t.get("owner") or "(unassigned)"


def graph(p):
    items = records(p)
    graph_ = {k: deps(t) for k,t in items.items()}
    dangling = sorted({d for ds in graph_.values() for d in ds if d not in items})
    if dangling:
        raise ValueError("unknown prerequisites: " + ", ".join(dangling))
    return graph_


def topo(p):
    g = graph(p)
    try:
        return list(TopologicalSorter({k: sorted(g[k]) for k in sorted(g)}).static_order())
    except CycleError as e:
        raise ValueError(f"dependency cycle: {e.args[1]}") from e


def reverse(g):
    result = {k: set() for k in g}
    for k, ds in g.items():
        for d in ds:
            result[d].add(k)
    return result


def closure(g, key):
    seen = {key}
    queue = [key]
    while queue:
        for dep in g[queue.pop()]:
            if dep not in seen:
                seen.add(dep)
                queue.append(dep)
    return sorted(seen - {key})


def schedule(p):
    g, items = graph(p), records(p)
    starts, ends, predecessor = {}, {}, {}
    for k in topo(p):
        parent = max(sorted(g[k]), key=lambda x: ends[x], default=None)
        predecessor[k] = parent
        starts[k] = ends[parent] if parent else 0
        ends[k] = starts[k] + remaining(items[k])
    return starts, ends, predecessor


@operation("dependency_order", "Упорядочить работы так, чтобы каждая предпосылка предшествовала зависимой задаче.")
def dependency_order(p): return topo(p)


@operation("dependency_cycles", "Найти и показать одну замыкающуюся цепь предпосылок.")
def dependency_cycles(p):
    try:
        list(TopologicalSorter(graph(p)).static_order())
    except CycleError as e:
        return e.args[1]
    return []


@operation("unknown_prerequisites", "Найти ссылки на отсутствующие в плане задачи.")
def unknown_prerequisites(p):
    items = records(p)
    return {k:sorted(missing) for k,t in items.items() if (missing := deps(t)-items.keys())}


@operation("prerequisite_tree", "Собрать всех прямых и косвенных предшественников выбранной работы.")
def prerequisite_tree(p): return closure(graph(p), focus(p)["id"])


@operation("impact_radius", "Вычислить работы, затронутые изменением выбранной задачи.")
def impact_radius(p): return closure(reverse(graph(p)), focus(p)["id"])


@operation("dependency_roots", "Выделить задачи без предпосылок.")
def dependency_roots(p): return sorted(k for k,ds in graph(p).items() if not ds)


@operation("dependency_deliverables", "Найти конечные результаты, от которых уже не зависят другие задачи.")
def dependency_deliverables(p): return sorted(k for k,ds in reverse(graph(p)).items() if not ds)


@operation("ready_queue", "Собрать очередь открытых задач, у которых завершены все предпосылки.")
def ready_queue(p):
    items, g = records(p), graph(p)
    return sorted(t["id"] for t in open_items(p) if all(items[d].get("status")=="done" for d in g[t["id"]]))


@operation("blocker_map", "Назвать непосредственные незавершённые предпосылки каждой заблокированной задачи.")
def blocker_map(p):
    items, g = records(p), graph(p)
    return {t["id"]: blockers for t in open_items(p) if (blockers := sorted(d for d in g[t["id"]] if items[d].get("status")!="done"))}


@operation("parallel_waves", "Разделить оставшийся граф на этапы параллельного выполнения.")
def parallel_waves(p):
    g = graph(p)
    outstanding = {t["id"] for t in open_items(p)}
    levels = {}
    for k in topo(p):
        if k in outstanding:
            levels[k]=1+max((levels[d] for d in g[k] if d in outstanding), default=0)
    return [sorted(k for k,n in levels.items() if n==level) for level in sorted(set(levels.values()))]


@operation("critical_chain", "Найти длиннейшую цепь оставшихся трудозатрат при неограниченном параллелизме.")
def critical_chain(p):
    _, ends, parent = schedule(p)
    k = max(sorted(ends), key=ends.get, default=None)
    path = []
    while k is not None:
        path.append(k)
        k = parent[k]
    return list(reversed(path))


@operation("critical_hours", "Рассчитать нижнюю границу времени исполнения по зависимостям в часах.")
def critical_hours(p): return max(schedule(p)[1].values(), default=0)


@operation("earliest_starts", "Рассчитать ранний старт каждой задачи по оставшимся часам её предшественников.")
def earliest_starts(p): return schedule(p)[0]


@operation("dependency_slack", "Рассчитать резерв времени каждой задачи до конца проекта в часах.")
def dependency_slack(p):
    starts, ends, _ = schedule(p)
    rev = reverse(graph(p))
    latest = {}
    for k in reversed(topo(p)):
        deadline = min((latest[x] for x in rev[k]),default=max(ends.values(),default=0))
        latest[k] = deadline-(ends[k]-starts[k])
    return {k:v-starts[k] for k,v in latest.items()}


@operation("redundant_dependencies", "Обнаружить прямые предпосылки, уже покрытые косвенной цепочкой.")
def redundant_dependencies(p):
    g = graph(p)
    topo(p)
    out = []
    for k, ds in g.items():
        for d in sorted(ds):
            if any(d in closure(g,other) for other in ds-{d}):
                out.append([k,d])
    return out


@operation("due_today", "Выбрать открытые задачи со сроком сегодня.")
def due_today(p): return [t["id"] for t in open_items(p) if t.get("due") == current(p).isoformat()]


@operation("overdue_days", "Вычислить для каждой просроченной задачи величину отставания в днях.")
def overdue_days(p): return {t["id"]:(current(p)-day(t["due"])).days for t in open_items(p) if t.get("due") and day(t["due"])<current(p)}


@operation("due_window", "Отобрать открытые задачи со сроком в следующие N календарных дней включительно.")
def due_window(p):
    now = current(p)
    until = now + timedelta(days=int(number(p.get("days",7))))
    return sorted(t["id"] for t in open_items(p) if t.get("due") and now<=day(t["due"])<=until)


@operation("deadline_agenda", "Построить календарь открытых работ по точным датам сдачи.")
def deadline_agenda(p):
    agenda=defaultdict(list)
    for t in open_items(p):
        if t.get("due"): agenda[day(t["due"]).isoformat()].append(t["id"])
    return dict(sorted(agenda.items()))


@operation("unplanned_dates", "Выявить открытые работы, для которых ещё не указан срок.")
def unplanned_dates(p): return [t["id"] for t in open_items(p) if not t.get("due")]


@operation("delivery_collision", "Найти совпадающие сроки двух или более открытых работ одного исполнителя.")
def delivery_collision(p):
    groups=defaultdict(list)
    for t in open_items(p):
        if t.get("due") and t.get("owner"): groups[(owner(t),t["due"])].append(t["id"])
    return [{"owner":o,"due":d,"tasks":ks} for (o,d),ks in sorted(groups.items()) if len(ks)>1]


@operation("inverted_deadlines", "Найти предпосылки, назначенные на более позднюю дату, чем их потребители.")
def inverted_deadlines(p):
    items=records(p)
    return [[d,k] for k,ds in graph(p).items() for d in sorted(ds) if items[k].get("due") and items[d].get("due") and day(items[d]["due"])>day(items[k]["due"])]


@operation("milestone_calendar", "Вывести календарь этапов с оставшимися днями до их сдачи.")
def milestone_calendar(p):
    return sorted([{"id":t["id"],"due":t["due"],"days":(day(t["due"])-current(p)).days} for t in open_items(p) if t.get("milestone") and t.get("due")],key=lambda t:t["due"])


@operation("next_deadline", "Найти ближайший будущий срок открытой работы и все задачи на этот день.")
def next_deadline(p):
    agenda=deadline_agenda(p)
    d=next((d for d in agenda if day(d)>=current(p)),None)
    return {"date":d,"tasks":agenda.get(d,[])}


@operation("due_week_effort", "Суммировать остатки работ по календарным неделям их сдачи.")
def due_week_effort(p):
    result=Counter()
    for t in open_items(p):
        if t.get("due"):
            iso=day(t["due"]).isocalendar()
            result[f"{iso.year}-W{iso.week:02}"]+=remaining(t)
    return dict(result)


@operation("remaining_hours", "Посчитать остаток часов для каждой работы с учётом завершения и списаний.")
def remaining_hours(p): return {k:remaining(t) for k,t in records(p).items()}


@operation("estimate_overruns", "Найти задачи, где фактические затраты превысили оценку, и вычислить превышение.")
def estimate_overruns(p): return {k:spent(t)-hours(t) for k,t in records(p).items() if spent(t)>hours(t)}


@operation("owner_load", "Распределить оставшиеся часы между исполнителями.")
def owner_load(p):
    amounts=Counter()
    for t in open_items(p): amounts[owner(t)]+=remaining(t)
    return dict(amounts)


@operation("owner_capacity_days", "Оценить длительность очереди каждого исполнителя по его доступным часам в день.")
def owner_capacity_days(p):
    caps=p.get("capacities",{})
    return {o:(ceil(h/number(caps[o])) if caps.get(o) and number(caps[o])>0 else None) for o,h in owner_load(p).items()}


@operation("capacity_shortage", "Посчитать недостающие часы каждого исполнителя в заданном горизонте.")
def capacity_shortage(p):
    caps=p.get("capacities",{})
    days=number(p.get("days",1))
    return {o:deficit for o,h in owner_load(p).items() if (deficit:=h-number(caps.get(o,0))*days)>0}


@operation("unassigned_effort", "Сосчитать неприсвоенную трудоёмкость и указать задачи, формирующие её.")
def unassigned_effort(p):
    items=[t for t in open_items(p) if not t.get("owner")]
    return {"hours":sum(map(remaining,items)),"ids":[t["id"] for t in items]}


@operation("cost_forecast", "Оценить оставшуюся стоимость труда по заданным почасовым ставкам и отметить неизвестные ставки.")
def cost_forecast(p):
    rates=p.get("rates",{})
    loads=owner_load(p)
    return {"estimated_cost":sum(h*number(rates[o]) for o,h in loads.items() if o in rates),"missing_rates":sorted(loads.keys()-rates.keys())}


@operation("effort_progress", "Вычислить выполненную долю запланированного объёма с весом по оценке часов.")
def effort_progress(p):
    items=list(records(p).values())
    total=sum(map(hours,items))
    return (total-sum(map(remaining,items)))/total if total else None


@operation("owner_handoffs", "Найти переходы ответственности между исполнителями по рёбрам графа.")
def owner_handoffs(p):
    items=records(p)
    return [{"from_task":d,"to_task":k,"from_owner":owner(items[d]),"to_owner":owner(items[k])} for k,ds in graph(p).items() for d in sorted(ds) if owner(items[k])!=owner(items[d])]


@operation("work_in_progress", "Подсчитать число начатых работ по каждому исполнителю.")
def work_in_progress(p): return dict(Counter(owner(t) for t in open_items(p) if t.get("status")=="active"))


@operation("longest_open", "Найти самую давно созданную открытую работу и её возраст в днях.")
def longest_open(p):
    t=min((t for t in open_items(p) if t.get("created")),key=lambda t:day(t["created"]),default=None)
    return {"id":t["id"],"days":(current(p)-day(t["created"])).days} if t else None


@operation("duration_history", "Вычислить календарную длительность завершённых задач по фактическим датам.")
def duration_history(p):
    return {k:(day(t["completed"])-day(t["started"])).days for k,t in records(p).items() if t.get("completed") and t.get("started")}


@operation("median_cycle_days", "Оценить обычную длительность завершённой работы по медиане фактических циклов.")
def median_cycle_days(p):
    ds=list(duration_history(p).values())
    return median(ds) if ds else None


@operation("deadline_accuracy", "Подсчитать своевременные и опоздавшие завершения по фактическим датам.")
def deadline_accuracy(p):
    completed=[t for t in records(p).values() if t.get("completed") and t.get("due")]
    late=sum(day(t["completed"])>day(t["due"]) for t in completed)
    return {"on_time":len(completed)-late,"late":late,"assessed":len(completed)}


@operation("missing_estimates", "Найти открытые задачи без исходной оценки труда.")
def missing_estimates(p): return [t["id"] for t in open_items(p) if t.get("estimate") is None]


@operation("zero_capacity_owners", "Показать ответственных с ненулевой нагрузкой и отсутствующей доступностью.")
def zero_capacity_owners(p): return [o for o,h in owner_load(p).items() if h and not number(p.get("capacities",{}).get(o,0))]


def altered(p, **values):
    key=focus(p)["id"]
    return [dict(deepcopy(t),**values) if t["id"]==key else deepcopy(t) for t in records(p).values()]


@operation("rename_task", "Обновить заголовок выбранной работы и вернуть новый план.")
def rename_task(p):
    title=p["title"].strip()
    if not title: raise ValueError("empty title")
    return altered(p,title=title)


@operation("assign_task", "Назначить ответственного выбранной задаче.")
def assign_task(p): return altered(p,owner=p["target_owner"])


@operation("release_owner", "Вернуть выбранную задачу в очередь без ответственного.")
def release_owner(p): return altered(p,owner=None)


@operation("reschedule_task", "Перенести назначенный срок выбранной задачи на новую дату.")
def reschedule_task(p): return altered(p,due=day(p["target_date"]).isoformat())


@operation("shift_task_days", "Сдвинуть текущий срок выбранной работы на заданное число календарных дней.")
def shift_task_days(p):
    target=day(focus(p)["due"])+timedelta(days=int(p["shift"]))
    return altered(p,due=target.isoformat())


@operation("log_effort", "Добавить запись трудозатрат к накопленным часам выбранной задачи.")
def log_effort(p): return altered(p,spent=spent(focus(p))+number(p["hours"]))


@operation("revise_estimate", "Записать пересмотренную общую оценку трудоёмкости.")
def revise_estimate(p): return altered(p,estimate=number(p["hours"]))


@operation("start_ready_task", "Начать доступную задачу с проверкой незавершённых предпосылок и выставить дату старта.")
def start_ready_task(p):
    t=focus(p)
    if t["id"] not in ready_queue(p): raise ValueError("task is not ready")
    return altered(p,status="active",started=t.get("started") or current(p).isoformat())


@operation("finish_task", "Завершить выбранную работу с проверкой предпосылок и записью фактической даты.")
def finish_task(p):
    t=focus(p)
    if t["id"] in blocker_map(p): raise ValueError("unresolved prerequisites")
    return altered(p,status="done",completed=t.get("completed") or current(p).isoformat())


@operation("reopen_task", "Вернуть выбранную работу в план и снять отметку фактического завершения.")
def reopen_task(p): return altered(p,status="todo",completed=None)


@operation("add_dependency", "Добавить предварительную работу с проверкой существования цели и отсутствия циклов.")
def add_dependency(p):
    t=focus(p)
    change=altered(p,deps=sorted(deps(t)|{p["other_id"]}))
    topo(dict(p,tasks=change))
    return change


@operation("remove_dependency", "Убрать только выбранную связь с предшественником.")
def remove_dependency(p): return altered(p,deps=sorted(deps(focus(p))-{p["other_id"]}))


@operation("add_label", "Добавить метку выбранной работы без дублей.")
def add_label(p): return altered(p,labels=sorted(set(focus(p).get("labels",[]))|{p["label"]}))


@operation("remove_label", "Снять выбранную метку, сохранив остальные.")
def remove_label(p): return altered(p,labels=sorted(set(focus(p).get("labels",[]))-{p["label"]}))


@operation("promote_milestone", "Пометить выбранную задачу контрольной точкой плана.")
def promote_milestone(p): return altered(p,milestone=True)


@operation("set_priority", "Записать целочисленный приоритет выбранной задачи.")
def set_priority(p): return altered(p,priority=int(p["priority"]))


@operation("append_note", "Добавить датированную заметку в историю задачи.")
def append_note(p): return altered(p,notes=[*focus(p).get("notes",[]),{"date":current(p).isoformat(),"text":p["note"]}])


@operation("insert_task", "Вставить новую задачу с проверкой уникальности идентификатора и связности плана.")
def insert_task(p):
    tasks=[*deepcopy(p.get("tasks",[])),deepcopy(p["new_task"])]
    topo(dict(p,tasks=tasks))
    return tasks


@operation("remove_finished_leaf", "Удалить завершённую задачу без зависимых потребителей.")
def remove_finished_leaf(p):
    t=focus(p)
    if t.get("status")!="done" or reverse(graph(p))[t["id"]]: raise ValueError("expected completed leaf")
    return [deepcopy(v) for k,v in records(p).items() if k!=t["id"]]


@operation("transfer_open_work", "Передать все открытые задачи одного исполнителя другому.")
def transfer_open_work(p):
    return [dict(deepcopy(t),owner=p["target_owner"]) if owner(t)==p["source_owner"] and t.get("status")!="done" else deepcopy(t) for t in records(p).values()]


@operation("shift_branch", "Перенести сроки выбранной работы и всех её потомков на одно число дней.")
def shift_branch(p):
    affected={focus(p)["id"],*impact_radius(p)}
    return [dict(deepcopy(t),due=(day(t["due"])+timedelta(days=int(p["shift"]))).isoformat()) if t["id"] in affected and t.get("due") and t.get("status")!="done" else deepcopy(t) for t in records(p).values()]


@operation("rollover_unfinished", "Перенести сроки просроченных открытых задач на указанную дату.")
def rollover_unfinished(p):
    late=overdue_days(p)
    target=day(p["target_date"])
    if target<current(p): raise ValueError("target is overdue")
    return [dict(deepcopy(t),due=target.isoformat()) if k in late else deepcopy(t) for k,t in records(p).items()]


def version_pair(p): return records(p,"baseline"), records(p)


@operation("added_work", "Найти задачи, появившиеся после исходной версии.")
def added_work(p):
    old,new=version_pair(p)
    return sorted(new.keys()-old.keys())


@operation("removed_work", "Найти идентификаторы задач, исчезнувшие относительно исходной версии.")
def removed_work(p):
    old,new=version_pair(p)
    return sorted(old.keys()-new.keys())


def differences(p, field):
    old,new=version_pair(p)
    return {k:{"before":old[k].get(field),"after":new[k].get(field)} for k in sorted(old.keys()&new.keys()) if old[k].get(field)!=new[k].get(field)}


for key,field,description in [
    ("ownership_changes","owner","Выявить передачи ответственности между двумя версиями плана."),
    ("status_transitions","status","Вывести фактические переходы состояний задач между версиями."),
    ("priority_changes","priority","Указать изменившиеся приоритеты с прежним и новым значениями."),
    ("retitled_work","title","Сопоставить прежние и новые формулировки названий задач."),
    ("revised_estimates","estimate","Показать прежние и новые оценки трудозатрат одних и тех же задач."),
]:
    operation(key,description)(partial(differences,field=field))


@operation("deadline_drift", "Рассчитать смещение срока каждой сопоставимой работы в календарных днях.")
def deadline_drift(p):
    return {k:(day(c["after"])-day(c["before"])).days for k,c in differences(p,"due").items() if c["after"] and c["before"]}


@operation("dependency_delta", "Показать добавленные и снятые зависимости для сохранившихся работ.")
def dependency_delta(p):
    old,new=version_pair(p)
    out={}
    for k in sorted(old.keys()&new.keys()):
        a,b=deps(old[k]),deps(new[k])
        if a!=b: out[k]={"added":sorted(b-a),"removed":sorted(a-b)}
    return out


@operation("scope_growth_hours", "Посчитать изменение общего запланированного объёма между версиями.")
def scope_growth_hours(p):
    old,new=version_pair(p)
    return sum(map(hours,new.values()))-sum(map(hours,old.values()))


@operation("restore_task_version", "Вернуть одну задачу из базовой версии и проверить целостность зависимостей.")
def restore_task_version(p):
    old,new=version_pair(p)
    k=p["task_id"]
    if k not in old: raise ValueError("task absent from baseline")
    new[k]=old[k]
    out=deepcopy(list(new.values()))
    topo(dict(p,tasks=out))
    return out


def decision(p):
    items=records(p,"decisions")
    if p.get("decision_id") not in items: raise ValueError("unknown decision_id")
    return items[p["decision_id"]]


def update_decision(p, **fields):
    key=decision(p)["id"]
    return [dict(deepcopy(d),**fields) if k==key else deepcopy(d) for k,d in records(p,"decisions").items()]


@operation("open_choices", "Собрать ещё не принятые решения вместе с доступными альтернативами.")
def open_choices(p):
    return {k:list(d.get("options",{})) for k,d in records(p,"decisions").items() if d.get("selected") is None}


@operation("option_utilities", "Сравнить альтернативы по взвешенной сумме оценок на согласованных критериях.")
def option_utilities(p):
    d=decision(p)
    weights=d.get("weights",{})
    if not weights: raise ValueError("decision requires criterion weights")
    return {opt:sum(number(w)*float(scores[c]) for c,w in weights.items()) for opt,scores in d["options"].items()}


@operation("option_frontier", "Оставить альтернативы, которые не проигрывают другой сразу по всем критериям.")
def option_frontier(p):
    d=decision(p)
    options=d["options"]
    cs=list(d["weights"])
    def dominant(a,b):
        return all(float(a[c])>=float(b[c]) for c in cs) and any(float(a[c])>float(b[c]) for c in cs)
    return sorted(k for k,b in options.items() if not any(dominant(a,b) for a in options.values()))


@operation("decision_flip_weight", "Рассчитать порог веса выбранного критерия, при котором две альтернативы равны.")
def decision_flip_weight(p):
    d=decision(p)
    c=p["criterion"]
    weights=d["weights"]
    if c not in weights: raise ValueError("unknown criterion")
    a,b=[d["options"][p[k]] for k in ("option","other_option")]
    diff=float(a[c])-float(b[c])
    if not diff: return None
    fixed=sum(number(w)*(float(a[k])-float(b[k])) for k,w in weights.items() if k!=c)
    boundary=-fixed/diff
    return boundary if boundary>=0 else None


@operation("decision_tradeoff", "Показать выигрыш и потери выбранной альтернативы по каждому критерию против второй.")
def decision_tradeoff(p):
    d=decision(p)
    a,b=[d["options"][p[k]] for k in ("option","other_option")]
    return {c:float(a[c])-float(b[c]) for c in d["weights"]}


@operation("choose_option", "Зафиксировать выбор из существующих вариантов с причиной и датой.")
def choose_option(p):
    d=decision(p)
    opt=p["option"]
    if opt not in d["options"]: raise ValueError("unknown option")
    return update_decision(p,selected=opt,reason=p["reason"],decided_at=current(p).isoformat())


@operation("reopen_choice", "Пересмотреть принятое решение с сохранением прежнего выбора в его истории.")
def reopen_choice(p):
    d=decision(p)
    history=deepcopy(d.get("history",[]))
    if d.get("selected") is not None:
        history.append({"selected":d["selected"],"reason":d.get("reason"),"decided_at":d.get("decided_at")})
    return update_decision(p,selected=None,reason=None,decided_at=None,history=history)


@operation("assumption_changes", "Сопоставить исходные предпосылки решений с новыми наблюдаемыми фактами.")
def assumption_changes(p):
    facts=p.get("facts",{})
    result={}
    for k,d in records(p,"decisions").items():
        changed={a:{"was":v,"now":facts[a]} for a,v in d.get("assumptions",{}).items() if a in facts and facts[a]!=v}
        if changed: result[k]=changed
    return result


@operation("decision_affected_work", "Найти задачи, зависящие от выбранного решения, включая косвенных потребителей.")
def decision_affected_work(p):
    idx,g=records(p),reverse(graph(p))
    key=decision(p)["id"]
    ids={k for k,t in idx.items() if key in t.get("decision_ids",[])}
    return sorted(ids|{v for k in ids for v in closure(g,k)})


@operation("decision_queue", "Упорядочить открытые решения по числу затронутых работ.")
def decision_queue(p):
    choices=open_choices(p)
    items=[{"id":k,"affected_tasks":len(decision_affected_work(dict(p,decision_id=k)))} for k in choices]
    return sorted(items,key=lambda t:(-t["affected_tasks"],t["id"]))


@operation("criteria_gaps", "Указать, какие критерии остались неоценёнными для каждой альтернативы.")
def criteria_gaps(p):
    d=decision(p)
    return {opt:sorted(set(d.get("weights",{}))-scores.keys()) for opt,scores in d["options"].items()}


@operation("decision_log", "Восстановить хронологию принятых решений с их исходными аргументами.")
def decision_log(p):
    events=[]
    for k,d in records(p,"decisions").items():
        for item in [*d.get("history",[]),d]:
            if item.get("decided_at") and item.get("selected") is not None:
                events.append({"id":k,"date":day(item["decided_at"]).isoformat(),"option":item["selected"],"reason":item.get("reason")})
    return sorted(events,key=lambda v:(v["date"],v["id"]))


@operation("next_action", "Предложить доступную задачу по приоритету, затем сроку и остатку усилий.")
def next_action(p):
    items=records(p)
    keys=sorted(ready_queue(p),key=lambda k:(-int(items[k].get("priority",0)),items[k].get("due") or "9999-12-31",remaining(items[k]),k))
    return deepcopy(items[keys[0]]) if keys else None


@operation("timebox_work", "Заполнить ограниченный интервал доступными задачами по приоритету без превышения бюджета.")
def timebox_work(p):
    items=records(p)
    keys=sorted(ready_queue(p),key=lambda k:(-int(items[k].get("priority",0)),remaining(items[k]),k))
    budget=number(p["hours"])
    selected=[]
    for k in keys:
        cost=remaining(items[k])
        if cost<=budget:
            budget-=cost
            selected.append(k)
    return {"tasks":selected,"unused_hours":budget}


@operation("quick_unlock", "Найти доступную задачу, чьё завершение разблокирует больше всего непосредственных работ.")
def quick_unlock(p):
    blockers=blocker_map(p)
    candidates={k:sorted(j for j,ls in blockers.items() if ls==[k]) for k in ready_queue(p)}
    if not candidates: return None
    k=min(candidates,key=lambda k:(-len(candidates[k]),k))
    return {"id":k,"newly_ready":candidates[k]}


@operation("completion_simulation", "Смоделировать завершение выбранной работы и вернуть изменения доступной очереди.")
def completion_simulation(p):
    previous=set(ready_queue(p))
    updated=dict(p,tasks=finish_task(p))
    after=set(ready_queue(updated))
    return {"newly_ready":sorted(after-previous),"removed_from_queue":sorted(previous-after),"remaining_total":sum(remaining_hours(updated).values())}


@operation("delay_simulation", "Смоделировать дополнительные часы выбранной работы и оценить продление критического пути.")
def delay_simulation(p):
    t=focus(p)
    if t.get("status")=="done": raise ValueError("expected open task")
    revised=altered(p,estimate=max(hours(t),spent(t))+number(p["hours"]))
    before=critical_hours(p)
    after=critical_hours(dict(p,tasks=revised))
    return {"before_hours":before,"after_hours":after,"extension":after-before}


@operation("fast_track_benefit", "Смоделировать снятие заданной зависимости и рассчитать сэкономленные часы критического пути.")
def fast_track_benefit(p):
    if p["other_id"] not in deps(focus(p)): raise ValueError("missing dependency")
    changed=dict(p,tasks=remove_dependency(p))
    return {"saved_hours":critical_hours(p)-critical_hours(changed),"new_chain":critical_chain(changed)}


@operation("resource_swap", "Оценить изменение максимального числа рабочих дней при передаче открытой задачи другому исполнителю.")
def resource_swap(p):
    if focus(p).get("status")=="done": raise ValueError("expected open task")
    after=dict(p,tasks=assign_task(p))
    def bound(context):
        vals=list(owner_capacity_days(context).values())
        return None if None in vals else max(vals,default=0)
    return {"before":bound(p),"after":bound(after),"new_load":owner_load(after)}


@operation("parallel_owner_conflicts", "Найти группы задач одного этапа параллельной работы с общим ответственным.")
def parallel_owner_conflicts(p):
    idx=records(p)
    result=[]
    for wave,ids in enumerate(parallel_waves(p),1):
        by_owner=defaultdict(list)
        for k in ids:
            if idx[k].get("owner"): by_owner[owner(idx[k])].append(k)
        result.extend({"wave":wave,"owner":o,"tasks":ks} for o,ks in by_owner.items() if len(ks)>1)
    return result


@operation("idle_capacity", "Вычислить незанятые часы исполнителей в горизонте по их открытой очереди.")
def idle_capacity(p):
    loads=owner_load(p)
    return {o:max(0,number(cap)*number(p.get("days",1))-loads.get(o,0)) for o,cap in p.get("capacities",{}).items()}


@operation("closed_with_open_predecessors", "Найти отмеченные завершёнными работы с незакрытыми входящими зависимостями.")
def closed_with_open_predecessors(p):
    idx=records(p)
    return {k:unfinished for k,ds in graph(p).items() if idx[k].get("status")=="done" and (unfinished:=sorted(d for d in ds if idx[d].get("status")!="done"))}


@operation("invalid_date_order", "Найти задачи с невозможной хронологией создания, старта и фактического завершения.")
def invalid_date_order(p):
    out={}
    for k,t in records(p).items():
        dates=[(f,day(t[f])) for f in ("created","started","completed") if t.get(f)]
        errors=[[fa,fb] for i,(fa,a) in enumerate(dates) for fb,b in dates[i+1:] if a>b]
        if errors: out[k]=errors
    return out


@operation("label_index", "Построить обратный индекс задач по меткам.")
def label_index(p):
    groups=defaultdict(list)
    for k,t in records(p).items():
        for label in sorted(set(t.get("labels",[]))): groups[label].append(k)
    return dict(groups)


@operation("team_brief", "Сформировать сводку одного исполнителя с доступной работой, препятствиями и ближайшими сроками.")
def team_brief(p):
    who=p["target_owner"]
    keys={t["id"] for t in open_items(p) if owner(t)==who}
    return {"owner":who,"ready":sorted(keys&set(ready_queue(p))),"blocked":{k:v for k,v in blocker_map(p).items() if k in keys},"due":{d:sorted(keys&set(ids)) for d,ids in deadline_agenda(p).items() if keys&set(ids)}}


@operation("task_brief", "Подготовить карточку передачи выбранной работы со статусом, остатком, входами и результатами-потребителями.")
def task_brief(p):
    t=focus(p)
    g=graph(p)
    k=t["id"]
    return {"id":k,"title":t.get("title"),"owner":t.get("owner"),"due":t.get("due"),"status":t.get("status"),"remaining_hours":remaining(t),"prerequisites":sorted(g[k]),"consumers":sorted(reverse(g)[k])}


SAMPLE={
    "tasks":[
        {"id":"a","title":"Подготовить материалы","owner":"Ана","estimate":3,"spent":4,"status":"done","created":"2026-11-10","started":"2026-11-11","completed":"2026-11-12","due":"2026-11-12"},
        {"id":"b","title":"Собрать сцену","owner":"Борис","estimate":6,"spent":1,"status":"active","created":"2026-11-12","started":"2026-11-20","due":"2026-11-21","deps":["a"],"labels":["voice"],"decision_ids":["x"],"priority":4},
        {"id":"c","title":"Показать сцену","owner":"Ана","estimate":3,"status":"todo","due":"2026-11-25","deps":["b"],"milestone":True},
        {"id":"d","title":"Материалы печати","owner":"Ана","estimate":2,"status":"done","due":"2026-11-20","completed":"2026-11-21"},
        {"id":"e","title":"Монтаж","estimate":2,"status":"todo","due":"2026-11-22"},
    ],
    "baseline":[{"id":"a","title":"Собрать материалы","estimate":2,"status":"todo"},{"id":"b","title":"Черновик сцены","owner":"Ана","estimate":4,"status":"todo","due":"2026-11-20","deps":["a"]}],
    "today":"2026-11-22","days":2,"task_id":"b","other_id":"a","hours":4,"shift":2,"priority":3,"label":"voice",
    "target_owner":"Ана","source_owner":"Борис","target_date":"2026-11-24","rates":{"Ана":10,"Борис":12},"capacities":{"Ана":6,"Борис":2},
    "new_task":{"id":"start","title":"Начать озвучку","deps":["a"],"status":"todo"},"title":"Смонтировать сцену","note":"Уточнена пауза",
    "decisions":[{"id":"x","options":{"quiet":{"темп":2,"ясность":5},"fast":{"темп":5,"ясность":2}},"weights":{"темп":1,"ясность":2},"assumptions":{"voice":"recorded"},"history":[{"selected":"fast","decided_at":"2026-11-14","reason":"Срочный показ"}]}],
    "decision_id":"x","option":"quiet","other_option":"fast","criterion":"темп","reason":"Чётче слышен голос","facts":{"voice":"live"},
}
SAMPLES={k:SAMPLE for k in OPS}
SAMPLES["remove_finished_leaf"]=dict(SAMPLE,task_id="d")
SAMPLES["add_dependency"]=dict(SAMPLE,other_id="d")
