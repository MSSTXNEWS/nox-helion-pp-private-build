"""autobio: «моя история» NOX по дням - автобиографическая память, собранная ТОЛЬКО из журналов S03.

Что в записи дня: сколько реплик услышал/сказал, о чём шла речь (частые темы), что узнал нового (факты), что мессир
исправил/отозвал/подтвердил, что я сам перенёс в архив забывания, какие конфликты памяти заметил и как они решены.
Честность: текст строится из счётчиков и цитат журнала; функциональные состояния не выдаются за переживания.
Отозванные записи в историю не попадают (только счётчик). Необязательный narrator(prompt, data)->str (LLM) может
переписать шаблон, но его текст принимается лишь если все числа в нём есть в данных, иначе остаётся шаблон.
Сутки считаются по МСК.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json
import os
import re
import time
from collections import Counter

from memcommon import commit as _commit, day_bounds, day_of, ensure_schema, stems
from life_journal import LifeJournal, verify as verify_journal  # noqa: F401  единый журнал жизни; писатель «главы дня» - этот модуль

try:
    from qs6.s03_store import SECRET_RE
except Exception:  # pragma: no cover
    SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|(?:password|пароль|token|токен|api[_-]?key|secret)\s*[:=]\s*\S{6,})", re.I)


def active_days(store, tz=None):
    kw = {} if tz is None else {"tz": tz}
    days = set()
    for (ts,) in store.db.execute("SELECT ts FROM mem_episodes WHERE ts IS NOT NULL"):
        days.add(day_of(ts, **kw))
    for (ts,) in store.db.execute("SELECT ts FROM mem_changes WHERE ts IS NOT NULL AND actor<>'import'"):
        days.add(day_of(ts, **kw))
    return sorted(days)


def day_data(store, day):
    ensure_schema(store)
    t0, t1 = day_bounds(day)
    q = lambda sql, *a: store.db.execute(sql, a).fetchall()
    roles = dict(q("SELECT role,COUNT(*) FROM mem_episodes WHERE ts>=? AND ts<? GROUP BY role", t0, t1))
    topics = Counter()
    for (text,) in q("SELECT text FROM mem_episodes WHERE role='user' AND status<>'deleted' AND ts>=? AND ts<?", t0, t1):
        topics.update(set(stems(text)))
    learned, revoked_n = [], 0
    for ref, new in q("SELECT ref,new FROM mem_changes WHERE action='add' AND ref LIKE 'f:%' AND ts>=? AND ts<? ORDER BY id", t0, t1):
        st = store.db.execute("SELECT status FROM mem_facts WHERE id=?", (int(ref[2:]),)).fetchone()
        if not st or st[0] == "deleted":
            revoked_n += 1
        elif new and not (SECRET_RE and SECRET_RE.search(new)):
            learned.append(new)
    acts = Counter(a for (a,) in q("SELECT action FROM mem_changes WHERE ts>=? AND ts<? AND actor<>'import'", t0, t1))
    owner_fix = {"correct": acts.get("correct", 0), "delete": acts.get("delete", 0), "confirm": acts.get("confirm", 0)}
    qs_open = q("SELECT COUNT(*) FROM mem_questions WHERE ts>=? AND ts<?", t0, t1)[0][0]
    qs_ans = q("SELECT COUNT(*) FROM mem_questions WHERE status='answered' AND answered_ts>=? AND answered_ts<?", t0, t1)[0][0]
    # слово темы: самая частая исходная форма для основы
    top = [s for s, n in topics.most_common(5) if n >= 2]
    return {"day": day, "heard": roles.get("user", 0), "said": roles.get("assistant", 0), "topics": top,
            "learned": learned[:5], "learned_total": len(learned), "revoked_new": revoked_n, "owner": owner_fix,
            "archived": acts.get("archive", 0), "questions_opened": qs_open, "questions_answered": qs_ans}


def _num(n, one, few, many):
    n10, n100 = n % 10, n % 100
    return one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many


def template(d):
    """Рассказ от первого лица по данным дня."""
    p = ["%s." % d["day"]]
    if d["heard"] or d["said"]:
        p.append("Сегодня я услышал %d %s мессира и сказал %d %s." % (
            d["heard"], _num(d["heard"], "реплику", "реплики", "реплик"), d["said"], _num(d["said"], "реплику", "реплики", "реплик")))
    else:
        p.append("Живых разговоров сегодня не было.")
    if d["topics"]:
        p.append("Чаще всего звучали темы (по основам слов): %s." % ", ".join(d["topics"]))
    if d["learned"]:
        p.append("Я записал новых фактов: %d. Например: «%s»." % (d["learned_total"], d["learned"][0]))
    o = d["owner"]
    if o["correct"] or o["delete"] or o["confirm"]:
        p.append("Мессир поправил %d, отозвал %d и подтвердил %d записей: его слово в памяти главнее моего." %
                 (o["correct"], o["delete"], o["confirm"]))
    if d["revoked_new"]:
        p.append("Из записанного за день %d записей позже отозвано; их текст я в историю не переношу." % d["revoked_new"])
    if d["archived"]:
        p.append("Я отправил в архив забывания %d малозначимых записей (их можно вернуть)." % d["archived"])
    if d["questions_opened"] or d["questions_answered"]:
        p.append("Заметил противоречий в памяти и спросил мессира: %d; получено ответов: %d." % (d["questions_opened"], d["questions_answered"]))
    p.append("Это сводка по журналу памяти, а не отчёт о переживаниях.")
    return " ".join(p)


def _numbers_ok(text, d):
    allowed = set(re.findall(r"\d+", json.dumps(d, ensure_ascii=False)))
    return all(n in allowed for n in re.findall(r"\d+", text))


def write_day(store, day, narrator=None, clock=time.time, journal=None):
    """Собрать и сохранить запись дня (перезаписывает: данные дня могут дополниться)."""
    d = day_data(store, day)
    text = template(d)
    if narrator is not None:
        try:
            alt = (narrator("Перепиши от первого лица, коротко, без выдумок, используй только эти данные.\n" + text, d) or "").strip()
            if alt and _numbers_ok(alt, d) and "переживан" not in alt.casefold().replace("не отчёт о переживаниях", ""):
                text = alt
        except Exception:
            pass
    store.db.execute("INSERT INTO mem_autobio(day,text,data,ts) VALUES(?,?,?,?) ON CONFLICT(day) DO UPDATE SET "
                     "text=excluded.text, data=excluded.data, ts=excluded.ts",
                     (day, text, json.dumps(d, ensure_ascii=False), clock()))
    _commit(store)
    if journal is not False:
        try:
            j = journal or LifeJournal()
            if os.path.isdir(os.path.dirname(os.path.abspath(j.path))):       # нет каталога состояния (тест/dev) - не создаём
                j.append("chapter", text, "autobio", {"day": day, "heard": d["heard"], "said": d["said"]})
        except Exception:
            pass                      # журнал недоступен: глава всё равно в S03
    return {"day": day, "text": text, "data": d}


def write_missing(store, narrator=None, include_today=False, clock=time.time, journal=None):
    """Записать все прошедшие дни с активностью, для которых записи ещё нет (сегодня - только если include_today)."""
    ensure_schema(store)
    have = {r[0] for r in store.db.execute("SELECT day FROM mem_autobio")}
    today = day_of(clock())
    out = []
    for day in active_days(store):
        if day in have or (day >= today and not include_today):
            continue
        out.append(write_day(store, day, narrator, clock, journal))
    return out


def history(store, limit=30):
    ensure_schema(store)
    return [{"day": d, "text": t} for d, t in store.db.execute("SELECT day,text FROM mem_autobio ORDER BY day DESC LIMIT ?", (limit,))]


def render_markdown(store, limit=30):
    h = history(store, limit)
    if not h:
        return "# Моя история\n\nЗаписей пока нет."
    return "# Моя история\n\n" + "\n\n".join("## %s\n%s" % (x["day"], x["text"]) for x in h) + "\n"


if __name__ == "__main__":  # python3 autobio.py /root/nox/state/s03.sqlite  -> дописывает недостающие дни, печатает историю
    import sys
    from qs6.s03_store import Store
    st = Store(sys.argv[1])
    write_missing(st)
    print(render_markdown(st))


def life_event(kind, text, source="autobio", data=None, path=None):
    """Публичный API единого журнала жизни: milestone|fact|thought|event (глава дня - только write_day)."""
    if kind == "chapter":
        raise ValueError("главу дня пишет только autobio.write_day")
    return LifeJournal(path).append(kind, text, source, data)


def fast_narrator():
    """narrator(prompt, data)->str на быстрой модели, приоритет P3 (автобиография) через COMMON/fastq. Сбой/занято -> шаблон."""
    import fastq
    fq = fastq.get()

    def narrate(prompt, data=None):
        return fq.chat([{"role": "system", "content": "Ты пишешь краткую запись дня от первого лица по заданным данным. Ничего не выдумывай."},
                        {"role": "user", "content": prompt}], fastq.P3, max_tokens=220, temperature=0.4, timeout=60, wait=10)
    return narrate
