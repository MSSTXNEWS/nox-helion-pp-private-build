"""nox_intent: «Мозг замысла» v7.1 - память о выборах, версиях, возражениях, дозвучанном, идеях, уроках и вторых мыслях.

Хранилище: S03 (SQLite). Только НОВЫЕ таблицы intent_* (CREATE IF NOT EXISTS); существующие таблицы/факты не меняются.
Без LLM и без сети: правила и ключевые слова. Интерпретация/творчество (GLM) - вне модуля, модуль хранит и применяет результат.
API: Intent.handle(method, path, qs, body) -> (status, obj); подключается в nox_core одной вставкой (/intent/*).
Env: NOX_INTENT_DB (по умолчанию /root/nox/memory/s03.db; файл должен существовать), NOX_INTENT=off.
"""
import asyncio
import json
import os
import re
import sqlite3
import time
from urllib.parse import parse_qs

DEFAULT_DB = "/root/nox/memory/s03.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS intent_meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS intent_choices(
  id INTEGER PRIMARY KEY, ts REAL, project TEXT, scene TEXT, option TEXT NOT NULL, reason TEXT,
  reason_kind TEXT NOT NULL DEFAULT 'unknown',   -- unknown | context | taste
  context TEXT NOT NULL DEFAULT '[]',            -- теги условий, при которых отказ был оправдан
  status TEXT NOT NULL DEFAULT 'rejected');      -- rejected | returned | closed
CREATE TABLE IF NOT EXISTS intent_futures(
  id INTEGER PRIMARY KEY, ts REAL, project TEXT, scene TEXT, parent_a INTEGER, parent_b INTEGER,
  title TEXT, segments TEXT NOT NULL, diff TEXT, status TEXT NOT NULL DEFAULT 'draft', ops TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS intent_objections(
  id INTEGER PRIMARY KEY, ts REAL, project TEXT, scene TEXT, topic TEXT NOT NULL, owner_position TEXT, nox_position TEXT,
  sample TEXT, prior_ref TEXT, status TEXT NOT NULL DEFAULT 'open', resolution TEXT);
CREATE TABLE IF NOT EXISTS intent_delivered(
  id INTEGER PRIMARY KEY, ts REAL, conv TEXT, text TEXT NOT NULL, proposed_at REAL, delivered_words INTEGER,
  delivered_at REAL, chosen TEXT, chosen_at REAL, correction TEXT, resumed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS intent_idea_sleep(
  id INTEGER PRIMARY KEY, ts REAL, project TEXT, scene TEXT, idea TEXT NOT NULL, sketch TEXT, sources TEXT,
  status TEXT NOT NULL DEFAULT 'sleeping',       -- sleeping | too_early | shown | closed
  show_after REAL NOT NULL DEFAULT 0, early_count INTEGER NOT NULL DEFAULT 0, shown_at REAL, note TEXT);
CREATE TABLE IF NOT EXISTS intent_lessons(
  id INTEGER PRIMARY KEY, ts REAL, pair_a TEXT NOT NULL, pair_b TEXT NOT NULL, rule TEXT NOT NULL, scope_a TEXT NOT NULL DEFAULT '[]',
  scope_b TEXT NOT NULL DEFAULT '[]', examples INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS intent_lesson_uses(id INTEGER PRIMARY KEY, ts REAL, lesson_id INTEGER, context TEXT, picked TEXT, new_work TEXT);
CREATE TABLE IF NOT EXISTS intent_second_thoughts(
  id INTEGER PRIMARY KEY, ts REAL, project TEXT, advice TEXT NOT NULL, basis TEXT NOT NULL, revisit_if TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'standing',       -- standing | revisit_due | revised | kept
  last_check_ts REAL);
CREATE TABLE IF NOT EXISTS intent_mind_log(
  id INTEGER PRIMARY KEY, ts REAL, thought_id INTEGER, event TEXT, fact_ref TEXT, note TEXT);
"""
TABLES = ("choices", "futures", "objections", "delivered", "idea_sleep", "lessons", "lesson_uses", "second_thoughts", "mind_log")


def _j(x):
    return json.dumps(x, ensure_ascii=False)


def _tags(x):
    if isinstance(x, str):
        x = [t for t in re.split(r"[,;\s]+", x) if t]
    return sorted({str(t).lower() for t in (x or [])})


def _words(text):
    return re.findall(r"\S+", text or "")


class Intent:
    def __init__(self, db=None):
        self.db = db or os.environ.get("NOX_INTENT_DB") or DEFAULT_DB
        self.ready = False

    # ---------- база ----------
    def con(self):
        if not os.path.exists(self.db):
            raise FileNotFoundError("S03 не найден: " + self.db)       # S03 не создаём: это чужая память
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=10000")
        if not self.ready:
            c.executescript(SCHEMA)
            c.commit()
            self.ready = True
        return c

    def _q(self, sql, args=(), one=False, commit=False):
        c = self.con()
        try:
            cur = c.execute(sql, args)
            if commit:
                c.commit()
                return cur.lastrowid
            rows = [dict(r) for r in cur.fetchall()]
            return (rows[0] if rows else None) if one else rows
        finally:
            c.close()

    def _get(self, table, i):
        r = self._q("SELECT * FROM intent_%s WHERE id=?" % table, (i,), one=True)
        if not r:
            raise KeyError("%s %s не найден" % (table, i))
        return r

    # ---------- 1. память о цене выбора ----------
    def refuse(self, option, reason=None, context=(), reason_kind=None, project=None, scene=None):
        """Отказ от варианта. Без названной причины -> unknown (NOX не придумывает мотив и не предлагает вариант снова сам)."""
        kind = reason_kind or ("context" if reason and context else ("unknown" if not reason else "taste"))
        i = self._q("INSERT INTO intent_choices(ts,project,scene,option,reason,reason_kind,context) VALUES(?,?,?,?,?,?,?)",
                    (time.time(), project, scene, option, reason, kind, _j(_tags(context))), commit=True)
        return self._get("choices", i)

    def revisit_options(self, context, project=None):
        """Какие отказанные варианты можно предложить снова в новом контексте (теги условий). Правила:
        taste/unknown - никогда сами; context - только если ни один из тегов причины отказа не действует сейчас."""
        now, out = set(_tags(context)), []
        for r in self._q("SELECT * FROM intent_choices WHERE status='rejected' AND reason_kind='context'"):
            if project and r["project"] not in (None, project):
                continue
            blockers = set(json.loads(r["context"]))
            if blockers and not (blockers & now):
                out.append(dict(r, why="причина отказа (%s) сейчас не действует: %s" % (r["reason"], ", ".join(sorted(blockers)))))
        return out

    def mark_returned(self, i, closed=False):
        self._q("UPDATE intent_choices SET status=? WHERE id=?", ("closed" if closed else "returned", i), commit=True)
        return self._get("choices", i)

    # ---------- 2. монтаж двух будущих ----------
    def future_pair(self, a_segments, b_segments, project=None, scene=None, title=None):
        """Две версии одного фрагмента: сегменты - dict имя->содержимое. diff - имена сегментов, которые различаются."""
        diff = sorted(k for k in set(a_segments) | set(b_segments) if a_segments.get(k) != b_segments.get(k))
        ids = []
        for seg, tag in ((a_segments, "A"), (b_segments, "B")):
            ids.append(self._q("INSERT INTO intent_futures(ts,project,scene,title,segments,diff,status) VALUES(?,?,?,?,?,?,'original')",
                               (time.time(), project, scene, "%s %s" % (title or "версия", tag), _j(seg), _j(diff)), commit=True))
        return {"a": self._get("futures", ids[0]), "b": self._get("futures", ids[1]), "diff": diff}

    def future_compose(self, a_id, b_id, take, title=None):
        """take: {имя_сегмента: 'a'|'b'}. Остальные сегменты берутся из A. Результат - draft со ссылками на оригиналы и журналом операций."""
        a, b = self._get("futures", a_id), self._get("futures", b_id)
        sa, sb = json.loads(a["segments"]), json.loads(b["segments"])
        out, ops = dict(sa), []
        for name, src in take.items():
            if src not in ("a", "b"):
                raise ValueError("источник должен быть a или b")
            srcd = sa if src == "a" else sb
            if name not in srcd:
                raise KeyError("в версии %s нет сегмента %s" % (src, name))
            out[name] = srcd[name]
            ops.append({"segment": name, "from": src})
        i = self._q("INSERT INTO intent_futures(ts,project,scene,parent_a,parent_b,title,segments,diff,status,ops) VALUES(?,?,?,?,?,?,?,?,'draft',?)",
                    (time.time(), a["project"], a["scene"], a_id, b_id, title or "монтаж", _j(out), a["diff"], _j(ops)), commit=True)
        return self._get("futures", i)

    def future_edit(self, i, name, value):
        r = self._get("futures", i)
        if r["status"] != "draft":
            raise ValueError("оригиналы не редактируются; редактируется только draft")
        seg, ops = json.loads(r["segments"]), json.loads(r["ops"])
        seg[name] = value
        ops.append({"segment": name, "edit": True})
        self._q("UPDATE intent_futures SET segments=?, ops=? WHERE id=?", (_j(seg), _j(ops), i), commit=True)
        return self._get("futures", i)

    def future_undo(self, i):
        r = self._get("futures", i)
        ops = json.loads(r["ops"])
        if not ops or r["parent_a"] is None:
            raise ValueError("нечего отменять")
        last = ops.pop()
        if last.get("edit"):
            raise ValueError("правку текста отменить нельзя; пересоберите из оригиналов")
        a = json.loads(self._get("futures", r["parent_a"])["segments"])
        seg = json.loads(r["segments"])
        seg[last["segment"]] = a[last["segment"]]
        self._q("UPDATE intent_futures SET segments=?, ops=? WHERE id=?", (_j(seg), _j(ops), i), commit=True)
        return self._get("futures", i)

    # ---------- 3. возражение с образцом ----------
    def object_(self, topic, owner_position, nox_position, sample=None, prior_ref=None, project=None, scene=None):
        """Без образца возражение - гипотеза в одну фразу (sample=None); решение всегда за владельцем."""
        i = self._q("INSERT INTO intent_objections(ts,project,scene,topic,owner_position,nox_position,sample,prior_ref) VALUES(?,?,?,?,?,?,?,?)",
                    (time.time(), project, scene, topic, owner_position, nox_position, sample, prior_ref), commit=True)
        r = self._get("objections", i)
        r["kind"] = "образец" if sample else "гипотеза"
        return r

    def object_resolve(self, i, chosen):
        if chosen not in ("owner", "nox", "other"):
            raise ValueError("chosen: owner|nox|other")
        self._q("UPDATE intent_objections SET status='closed', resolution=? WHERE id=?", (chosen, i), commit=True)
        return self._get("objections", i)

    def object_open(self, project=None, scene=None):
        """Закрытый для этой сцены спор не поднимается снова."""
        return self._q("SELECT * FROM intent_objections WHERE status='open' AND (? IS NULL OR project=?) AND (? IS NULL OR scene=?)",
                       (project, project, scene, scene))

    # ---------- 4. что предложено / дозвучало / выбрано ----------
    def propose(self, text, conv="default"):
        i = self._q("INSERT INTO intent_delivered(ts,conv,text,proposed_at) VALUES(?,?,?,?)", (time.time(), conv, text, time.time()), commit=True)
        return self._get("delivered", i)

    def delivered(self, i, words):
        """Плеер сообщил: дозвучало N слов. Не больше длины текста."""
        r = self._get("delivered", i)
        n = max(0, min(int(words), len(_words(r["text"]))))
        self._q("UPDATE intent_delivered SET delivered_words=?, delivered_at=? WHERE id=?", (n, time.time(), i), commit=True)
        return self._get("delivered", i)

    def choose(self, i, what):
        self._q("UPDATE intent_delivered SET chosen=?, chosen_at=? WHERE id=?", (what, time.time(), i), commit=True)
        return self._get("delivered", i)

    def resume(self, i=None, conv="default", correction=None, user_read_words=None):
        """«Продолжай» после перебивания: с начала предложения, на котором оборвалось (первая пропущенная мысль) + поправка.
        user_read_words - если человек сам прочёл дальше, точка возврата сдвигается. Позиция неизвестна -> короткий ориентир."""
        r = self._get("delivered", i) if i else self._q("SELECT * FROM intent_delivered WHERE conv=? ORDER BY id DESC LIMIT 1", (conv,), one=True)
        if not r:
            raise KeyError("нет сохранённой реплики")
        w = _words(r["text"])
        pos = user_read_words if user_read_words is not None else r["delivered_words"]
        if correction:
            self._q("UPDATE intent_delivered SET correction=? WHERE id=?", (correction, r["id"]), commit=True)
        if pos is None:
            anchor = " ".join(w[:8])
            return {"id": r["id"], "position": "unknown", "anchor": "…" + anchor, "note": "устройство не сообщило позицию; предлагаю ориентир: начало реплики",
                    "correction": correction}
        pos = max(0, min(int(pos), len(w)))
        if pos >= len(w):
            return {"id": r["id"], "position": pos, "remaining": "", "note": "реплика дозвучала полностью", "correction": correction}
        # откат к началу предложения, в котором оборвалось: считаем «дозвучавшим» только полные предложения
        starts, k = [0], 0
        for idx, tok in enumerate(w):
            if re.search(r"[.!?…]+[\"»)]*$", tok) and idx + 1 < len(w):
                starts.append(idx + 1)
        k = max(s for s in starts if s <= pos)
        self._q("UPDATE intent_delivered SET resumed=resumed+1 WHERE id=?", (r["id"],), commit=True)
        return {"id": r["id"], "position": pos, "resume_from_word": k, "remaining": " ".join(w[k:]), "heard": " ".join(w[:pos]),
                "correction": correction or r["correction"], "chosen": r["chosen"]}

    # ---------- 5. право идеи на тишину ----------
    def idea_add(self, idea, project=None, scene=None, sketch=None, sources=None, show_after=0):
        i = self._q("INSERT INTO intent_idea_sleep(ts,project,scene,idea,sketch,sources,show_after) VALUES(?,?,?,?,?,?,?)",
                    (time.time(), project, scene, idea, sketch, _j(sources or []), show_after), commit=True)
        return self._get("idea_sleep", i)

    def idea_react(self, i, reaction, delay_s=86400 * 7):
        """too_early -> сдвиг момента показа (идея жива); not_fit -> ветка закрыта навсегда."""
        if reaction == "too_early":
            self._q("UPDATE intent_idea_sleep SET status='too_early', show_after=?, early_count=early_count+1 WHERE id=?",
                    (time.time() + delay_s, i), commit=True)
        elif reaction == "not_fit":
            self._q("UPDATE intent_idea_sleep SET status='closed' WHERE id=?", (i,), commit=True)
        else:
            raise ValueError("reaction: too_early|not_fit")
        return self._get("idea_sleep", i)

    def idea_due(self, project=None, scene=None, mark_shown=False):
        """Идеи, которые можно показать при возвращении к сцене/проекту. Закрытые и ещё не созревшие не выдаются."""
        rows = self._q("SELECT * FROM intent_idea_sleep WHERE status IN ('sleeping','too_early') AND show_after<=? "
                       "AND (? IS NULL OR project=?) AND (scene IS NULL OR ? IS NULL OR scene=?) ORDER BY id",
                       (time.time(), project, project, scene, scene))
        if mark_shown:
            for r in rows:
                self._q("UPDATE intent_idea_sleep SET status='shown', shown_at=? WHERE id=?", (time.time(), r["id"]), commit=True)
        return rows

    # ---------- 6. ученичество наоборот ----------
    def teach(self, pair_a, pair_b, rule, scope_a, scope_b):
        """Пара (выбранное/невыбранное) + правило + области применения (теги). Повторная пара с тем же правилом увеличивает examples."""
        r = self._q("SELECT * FROM intent_lessons WHERE rule=? AND status='active'", (rule,), one=True)
        if r:
            self._q("UPDATE intent_lessons SET examples=examples+1 WHERE id=?", (r["id"],), commit=True)
            return self._get("lessons", r["id"])
        i = self._q("INSERT INTO intent_lessons(ts,pair_a,pair_b,rule,scope_a,scope_b) VALUES(?,?,?,?,?,?)",
                    (time.time(), pair_a, pair_b, rule, _j(_tags(scope_a)), _j(_tags(scope_b))), commit=True)
        return self._get("lessons", i)

    def lesson_apply(self, context, new_work=None):
        """NOX сам применяет различие: по тегам контекста выбирает сторону пары. Возвращает выбор и основание (с пометкой «один пример»)."""
        ctx, out = set(_tags(context)), []
        for l in self._q("SELECT * FROM intent_lessons WHERE status='active'"):
            ha, hb = ctx & set(json.loads(l["scope_a"])), ctx & set(json.loads(l["scope_b"]))
            if bool(ha) == bool(hb):
                continue                                           # неоднозначно или не про это - не применяем
            picked = l["pair_a"] if ha else l["pair_b"]
            self._q("INSERT INTO intent_lesson_uses(ts,lesson_id,context,picked,new_work) VALUES(?,?,?,?,?)",
                    (time.time(), l["id"], _j(sorted(ctx)), picked, new_work), commit=True)
            out.append({"lesson": l["id"], "picked": picked, "rule": l["rule"], "matched": sorted(ha or hb),
                        "basis": "единственный пример" if l["examples"] == 1 else "%d примера(ов)" % l["examples"]})
        return out

    def learned(self):
        """«Чему ты научился?»: исходная пара, правило, основание и последнее применение."""
        res = []
        for l in self._q("SELECT * FROM intent_lessons WHERE status='active' ORDER BY id"):
            use = self._q("SELECT * FROM intent_lesson_uses WHERE lesson_id=? ORDER BY id DESC LIMIT 1", (l["id"],), one=True)
            res.append({"lesson": l["id"], "pair": [l["pair_a"], l["pair_b"]], "rule": l["rule"],
                        "basis": "единственный пример" if l["examples"] == 1 else "%d примера(ов)" % l["examples"], "next_choice": use})
        return res

    # ---------- «Мои вторые мысли» ----------
    def advise(self, advice, basis, revisit_if, project=None):
        """revisit_if: {"keywords":[...], "min_hits":N} - пересмотреть, когда в НОВОМ факте S03 встречается >= min_hits ключевых слов
        (по умолчанию все). Сопоставление по ключевым словам без LLM: это честное ограничение."""
        if not isinstance(revisit_if, dict) or not revisit_if.get("keywords"):
            raise ValueError("revisit_if.keywords обязателен")
        i = self._q("INSERT INTO intent_second_thoughts(ts,project,advice,basis,revisit_if) VALUES(?,?,?,?,?)",
                    (time.time(), project, advice, basis, _j(revisit_if)), commit=True)
        self._q("INSERT INTO intent_mind_log(ts,thought_id,event,note) VALUES(?,?,?,?)", (time.time(), i, "advised", advice), commit=True)
        return self._get("second_thoughts", i)

    def _fact_source(self, c):
        for t in ("mem_facts", "facts"):
            cols = {r["name"] for r in c.execute("PRAGMA table_info(%s)" % t)}
            for tc in ("text", "fact", "content", "value"):
                if tc in cols:
                    return t, tc
        return None, None

    def facts_cursor(self):
        r = self._q("SELECT v FROM intent_meta WHERE k='facts_cursor'", one=True)
        return int(r["v"]) if r else None

    def check_second_thoughts(self, since_rowid=None, limit=5000):
        """Периодическая проверка: новые факты S03 (rowid > курсор) против оснований действующих советов.
        Первый запуск без since_rowid ставит курсор на конец (старые факты не считаются «новыми»)."""
        c = self.con()
        try:
            t, tc = self._fact_source(c)
            if not t:
                return {"ok": False, "error": "в S03 нет таблицы фактов (mem_facts/facts)"}
            top = c.execute("SELECT COALESCE(MAX(rowid),0) FROM %s" % t).fetchone()[0]
            cur = since_rowid if since_rowid is not None else self.facts_cursor()
            if cur is None:
                c.execute("INSERT OR REPLACE INTO intent_meta VALUES('facts_cursor',?)", (str(top),))
                c.commit()
                return {"ok": True, "initialized_cursor": top, "triggered": []}
            rows = c.execute("SELECT rowid AS rid, %s AS txt FROM %s WHERE rowid>? ORDER BY rowid LIMIT ?" % (tc, t), (cur, limit)).fetchall()
            thoughts = [dict(r) for r in c.execute("SELECT * FROM intent_second_thoughts WHERE status IN ('standing','kept')")]
            trig = []
            for th in thoughts:
                cond = json.loads(th["revisit_if"])
                kws = [k.lower() for k in cond["keywords"]]
                need = int(cond.get("min_hits") or len(kws))
                for r in rows:
                    txt = str(r["txt"] or "").lower()
                    if sum(1 for k in kws if k in txt) >= need:
                        c.execute("UPDATE intent_second_thoughts SET status='revisit_due', last_check_ts=? WHERE id=?", (time.time(), th["id"]))
                        c.execute("INSERT INTO intent_mind_log(ts,thought_id,event,fact_ref,note) VALUES(?,?,?,?,?)",
                                  (time.time(), th["id"], "revisit_due", "%s:%s" % (t, r["rid"]), str(r["txt"])[:300]))
                        trig.append({"thought": th["id"], "fact": r["rid"], "message":
                                     "Тогда я посоветовал: «%s». Основание: %s. Появился факт: «%s». Основание, возможно, отпало - я бы пересмотрел." %
                                     (th["advice"], th["basis"], str(r["txt"])[:200])})
                        break
            c.execute("INSERT OR REPLACE INTO intent_meta VALUES('facts_cursor',?)", (str(rows[-1]["rid"] if rows else cur),))
            c.commit()
            return {"ok": True, "checked_facts": len(rows), "triggered": trig}
        finally:
            c.close()

    def rethink(self, i, revised, new_advice=None, note=None):
        """Закрыть вторую мысль: revised (совет изменён, прежний хранится в биографии) или kept (основание проверено, совет остаётся)."""
        th = self._get("second_thoughts", i)
        if revised:
            self._q("INSERT INTO intent_mind_log(ts,thought_id,event,note) VALUES(?,?,?,?)",
                    (time.time(), i, "revised", "было: %s; стало: %s; %s" % (th["advice"], new_advice, note or "")), commit=True)
            self._q("UPDATE intent_second_thoughts SET status='revised', advice=? WHERE id=?", (new_advice or th["advice"], i), commit=True)
        else:
            self._q("INSERT INTO intent_mind_log(ts,thought_id,event,note) VALUES(?,?,?,?)", (time.time(), i, "kept", note or ""), commit=True)
            self._q("UPDATE intent_second_thoughts SET status='kept' WHERE id=?", (i,), commit=True)
        return self._get("second_thoughts", i)

    def biography(self):
        return self._q("SELECT * FROM intent_mind_log ORDER BY id")

    # ---------- HTTP ----------
    def status(self):
        c = self.con()
        try:
            return {"db": self.db, "tables": {t: c.execute("SELECT COUNT(*) FROM intent_" + t).fetchone()[0] for t in TABLES},
                    "facts_cursor": self.facts_cursor()}
        finally:
            c.close()

    def handle(self, method, path, qs, body):
        """Маршруты /intent/*. Ошибки -> (4xx, {"error"}); отсутствие S03 -> 503."""
        q = {k: v[0] for k, v in parse_qs(qs or "").items()}
        b = body or {}
        p = path.rstrip("/")
        try:
            if method == "GET":
                if p == "/intent/status":
                    return 200, self.status()
                if p == "/intent/choices/revisit":
                    return 200, {"options": self.revisit_options(_tags(q.get("context", "")), q.get("project"))}
                if p == "/intent/objections":
                    return 200, {"open": self.object_open(q.get("project"), q.get("scene"))}
                if p == "/intent/ideas/due":
                    return 200, {"ideas": self.idea_due(q.get("project"), q.get("scene"), q.get("mark_shown") == "1")}
                if p == "/intent/lessons":
                    return 200, {"learned": self.learned()}
                if p == "/intent/second_thoughts/biography":
                    return 200, {"biography": self.biography()}
                if p == "/intent/resume":
                    return 200, self.resume(int(q["id"]) if q.get("id") else None, q.get("conv", "default"), q.get("correction"),
                                            int(q["read_words"]) if q.get("read_words") else None)
            elif method == "POST":
                m = {
                    "/intent/choices": lambda: self.refuse(b["option"], b.get("reason"), b.get("context", ()), b.get("reason_kind"), b.get("project"), b.get("scene")),
                    "/intent/choices/returned": lambda: self.mark_returned(int(b["id"]), bool(b.get("closed"))),
                    "/intent/futures": lambda: self.future_pair(b["a"], b["b"], b.get("project"), b.get("scene"), b.get("title")),
                    "/intent/futures/compose": lambda: self.future_compose(int(b["a_id"]), int(b["b_id"]), b["take"], b.get("title")),
                    "/intent/futures/edit": lambda: self.future_edit(int(b["id"]), b["segment"], b["value"]),
                    "/intent/futures/undo": lambda: self.future_undo(int(b["id"])),
                    "/intent/objections": lambda: self.object_(b["topic"], b.get("owner_position"), b.get("nox_position"), b.get("sample"), b.get("prior_ref"), b.get("project"), b.get("scene")),
                    "/intent/objections/resolve": lambda: self.object_resolve(int(b["id"]), b["chosen"]),
                    "/intent/delivered/propose": lambda: self.propose(b["text"], b.get("conv", "default")),
                    "/intent/delivered/played": lambda: self.delivered(int(b["id"]), b["words"]),
                    "/intent/delivered/choose": lambda: self.choose(int(b["id"]), b["chosen"]),
                    "/intent/ideas": lambda: self.idea_add(b["idea"], b.get("project"), b.get("scene"), b.get("sketch"), b.get("sources"), b.get("show_after", 0)),
                    "/intent/ideas/react": lambda: self.idea_react(int(b["id"]), b["reaction"], b.get("delay_s", 86400 * 7)),
                    "/intent/lessons": lambda: self.teach(b["pair_a"], b["pair_b"], b["rule"], b.get("scope_a", ()), b.get("scope_b", ())),
                    "/intent/lessons/apply": lambda: {"applied": self.lesson_apply(b.get("context", ()), b.get("new_work"))},
                    "/intent/second_thoughts": lambda: self.advise(b["advice"], b["basis"], b["revisit_if"], b.get("project")),
                    "/intent/second_thoughts/check": lambda: self.check_second_thoughts(b.get("since_rowid")),
                    "/intent/second_thoughts/rethink": lambda: self.rethink(int(b["id"]), bool(b.get("revised")), b.get("new_advice"), b.get("note")),
                }.get(p)
                if m:
                    return 200, m()
            return 404, {"error": "not_found"}
        except FileNotFoundError as e:
            return 503, {"error": str(e)}
        except (KeyError, ValueError, TypeError) as e:
            return 400, {"error": "%s: %s" % (type(e).__name__, e)}

    async def loop(self, interval=None):
        """Фон: «Мои вторые мысли» - периодическая проверка новых фактов (NOX_INTENT_INTERVAL, по умолчанию 3600 с)."""
        interval = interval or float(os.environ.get("NOX_INTENT_INTERVAL", "3600"))
        while True:
            try:
                await asyncio.to_thread(self.check_second_thoughts)
            except Exception:
                pass
            await asyncio.sleep(interval)


def attach():
    """None, если выключено (NOX_INTENT=off)."""
    return None if os.environ.get("NOX_INTENT", "on").lower() == "off" else Intent()
