"""consolidate: «сон памяти» - эпизоды -> факты/убеждения, значимость, забывание затуханием, конфликты -> вопрос владельцу.

Принципы (по литературе: MemoryBank - кривая Эббингауза R=exp(-t/S), S растёт с обращениями; A-MEM/Mem0 - связывание и
обновление при новых данных; Zep - время жизни фактов; Riverse-лестница уже в S03 считает уверенность):
  1. Эпизоды -> факты: прогон fact_extract по ещё не обработанным репликам владельца. Источник свидетельства
     'chat:<сессия>' - тот же, что у memory_layer.after_reply, поэтому повторная обработка НЕ накручивает уверенность.
     Отозванное владельцем (mem_revoked) не добавляется заново.
  2. Убеждения: тема (пара значимых основ), повторяющаяся в >=min_days РАЗНЫХ днях, -> гипотеза «Мессир регулярно
     возвращается к теме «...»». Каждый день - независимый источник 'consolidate:day:<дата>' (вид chat, не «сильный»),
     поэтому без подтверждения владельцем убеждение не выше уровня «подозрение». Текст стабилен (без счётчиков).
  3. Значимость 0..1 и сила следа S: забывание = архивация (status='archived', обратимо restore_archived), никогда -
     для pinned/owner_confirmed/ядра/уровня>=2. Эпизоды архивируются только после консолидации и по сроку.
  4. Конфликты: пары активных фактов с одной темой и разным значением/отрицанием -> вопрос владельцу в mem_questions.
     Сам ничего не решает; ответ владельца применяется через Corrector (подтвердить одно, отозвать другое).
Все изменения - только при apply=True; по умолчанию сухой прогон.
"""
import json
import math
import re
import time
from collections import Counter, defaultdict

from memcommon import commit as _commit, DAY, day_of, ensure_schema, norm_text, stems

PROTECTED_KINDS = ("core", "owner", "setting")
NEG = {"не", "нет", "никогда", "ни", "без"}
KIND_WEIGHT = {"core": 1.0, "owner": 1.0, "setting": 0.8, "fact": 0.3}


def _default_extractor(text):
    from qs6.fact_extract import extract
    return extract(text)


class Consolidator:
    def __init__(self, store, corrector=None, extractor=None, clock=time.time, base_days=7.0, forget_below=0.15,
                 episode_ttl_days=90, belief_min_days=3, belief_min_eps=4, max_open_questions=3,
                 max_forget_ratio=0.05, min_forget_cap=20):
        ensure_schema(store)
        self.s = store
        self.c = corrector
        self.extractor = extractor or _default_extractor
        self.clock = clock
        self.base_days, self.forget_below, self.episode_ttl = base_days, forget_below, episode_ttl_days
        self.belief_min_days, self.belief_min_eps, self.max_open = belief_min_days, belief_min_eps, max_open_questions
        self.max_forget_ratio, self.min_forget_cap = max_forget_ratio, min_forget_cap

    # ---------- значимость и затухание ----------
    def salience(self, f):
        """0..1: важность, уверенность, частота обращений, подтверждение владельцем, вид записи."""
        freq = min(1.0, math.log1p(f["access_count"]) / math.log(11))
        keep = 1.0 if (f["pinned"] or f["owner_confirmed"]) else 0.0
        return round(0.35 * f["importance"] + 0.25 * f["level"] / 3.0 + 0.15 * freq + 0.15 * keep +
                     0.10 * KIND_WEIGHT.get(f["kind"], 0.3), 4)

    def strength_days(self, f):
        """S (дни) по MemoryBank: растёт с обращениями, уровнем уверенности и значимостью."""
        return self.base_days * (1 + f["access_count"]) * (1 + f["level"]) * (1 + 2 * self.salience(f))

    def retention(self, f, now=None):
        now = now or self.clock()
        last = max(f["last_access"] or 0, f["updated"] or 0, f["created"] or 0)
        t = max(0.0, now - last) / DAY
        return math.exp(-t / self.strength_days(f))

    def protected(self, f):
        return bool(f["pinned"] or f["owner_confirmed"] or f["kind"] in PROTECTED_KINDS or f["level"] >= 2)

    def forget_candidates(self, now=None):
        now = now or self.clock()
        out = []
        for f in self.s.active_facts():
            if self.protected(f):
                continue
            r = self.retention(f, now)
            if r < self.forget_below:
                out.append({"ref": f["ref"], "text": f["text"], "retention": round(r, 4), "salience": self.salience(f),
                            "strength_days": round(self.strength_days(f), 1)})
        return sorted(out, key=lambda x: x["retention"])

    def forget(self, apply=False, now=None):
        """Архивировать затухшее. Эпизоды: консолидированные, старше TTL, не подтверждённые владельцем."""
        now = now or self.clock()
        facts = self.forget_candidates(now)
        total = self.s.stats()["facts"]
        cap = max(self.min_forget_cap, int(total * self.max_forget_ratio))   # предохранитель: не стирать пласт за один прогон
        capped = max(0, len(facts) - cap)
        facts = facts[:cap]
        eps = [{"ref": "e:%d" % i} for (i,) in self.s.db.execute(
            "SELECT e.id FROM mem_episodes e JOIN mem_consolidated c ON c.episode_id=e.id "
            "WHERE e.status='active' AND e.owner_confirmed=0 AND e.ts<?", (now - self.episode_ttl * DAY,))]
        if apply:
            for it in facts + eps:
                self._archive(it["ref"], "затухание: " + json.dumps({k: v for k, v in it.items() if k in ("retention", "salience")}))
            _commit(self.s)
        return {"facts": facts, "episodes": eps, "applied": bool(apply), "deferred_by_cap": capped}

    def _archive(self, ref, reason):
        table = "mem_facts" if ref.startswith("f:") else "mem_episodes"
        self.s.db.execute("UPDATE %s SET status='archived' WHERE id=? AND status='active'" % table, (int(ref[2:]),))
        self.s._fts_set(ref, None)
        self.s.db.execute("DELETE FROM mem_vectors WHERE ref=?", (ref,))
        self.s._log("consolidate", "archive", ref, None, None, reason)

    def restore_archived(self, ref):
        table = "mem_facts" if ref.startswith("f:") else "mem_episodes"
        i = int(ref[2:])
        if table == "mem_facts":
            key = self.s.db.execute("SELECT key FROM mem_facts WHERE id=? AND status='archived'", (i,)).fetchone()
            if not key:
                return False
            if self.s.db.execute("SELECT 1 FROM mem_facts WHERE key=? AND status='active'", (key[0],)).fetchone():
                return False
        self.s.db.execute("UPDATE %s SET status='active' WHERE id=? AND status='archived'" % table, (i,))
        rec = self.s.get(ref)
        if rec is None or rec.get("status") != "active":
            return False
        self.s._fts_set(ref, self.s.text_of(rec) + ((" " + rec["summary"]) if rec.get("summary") else ""))
        self.s._log("consolidate", "unarchive", ref, None, None, "восстановлено")
        _commit(self.s)
        return True

    # ---------- эпизоды -> факты и убеждения ----------
    def _new_user_episodes(self, limit):
        return self.s.db.execute(
            "SELECT id,ts,text,session FROM mem_episodes WHERE status='active' AND role='user' AND id NOT IN "
            "(SELECT episode_id FROM mem_consolidated) ORDER BY id LIMIT ?", (limit,)).fetchall()

    def consolidate_episodes(self, apply=False, limit=500):
        from correction import is_revoked
        added, blocked, done = [], [], []
        for eid, ts, text, sess in self._new_user_episodes(limit):
            for f in self.extractor(text):
                if is_revoked(self.s, f["text"]):
                    blocked.append(f["text"])
                    continue
                if apply:
                    fid = self.s.add_fact(f["text"], kind=f["kind"], source="chat:" + (sess or day_of(ts)),
                                          source_kind=f["source_kind"], ts=ts, actor="consolidate")
                    added.append({"ref": "f:%d" % fid, "text": f["text"], "episode": "e:%d" % eid})
                else:
                    added.append({"ref": None, "text": f["text"], "episode": "e:%d" % eid})
            done.append(eid)
        if apply:
            self.s.db.executemany("INSERT OR IGNORE INTO mem_consolidated(episode_id,ts) VALUES(?,?)",
                                  [(i, self.clock()) for i in done])
            _commit(self.s)
        return {"episodes": len(done), "facts": added, "blocked_revoked": blocked, "applied": bool(apply)}

    def beliefs(self, apply=False, since_days=60):
        """Темы-пары основ, повторяющиеся в >= belief_min_days разных днях -> гипотезы-убеждения (с подтверждениями по дням)."""
        from correction import is_revoked
        now = self.clock()
        topic_days, topic_eps, forms = defaultdict(set), Counter(), defaultdict(Counter)
        for ts, text in self.s.db.execute("SELECT ts,text FROM mem_episodes WHERE status='active' AND role='user' AND ts>=?",
                                          (now - since_days * DAY,)):
            toks = []
            for w in re.findall(r"[^\W\d_]+", text.casefold()):
                st = stems(w)
                if st:
                    toks.append((st[0], w))
            uniq = {}
            for st, w in toks:
                uniq.setdefault(st, w)
            keys = sorted(uniq)
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    p = (keys[i], keys[j])
                    topic_days[p].add(day_of(ts))
                    topic_eps[p] += 1
                    forms[p][(uniq[keys[i]], uniq[keys[j]])] += 1
        out = []
        for p, days in topic_days.items():
            if len(days) >= self.belief_min_days and topic_eps[p] >= self.belief_min_eps:
                a, b = forms[p].most_common(1)[0][0]
                out.append((len(days), topic_eps[p], p, "Мессир регулярно возвращается к теме «%s %s»" % (a, b), sorted(days)))
        out.sort(key=lambda x: (-x[0], -x[1], x[2]))
        res = []
        for ndays, neps, p, text, days in out[:20]:
            if is_revoked(self.s, text):
                continue
            rec = {"text": text, "days": ndays, "episodes": neps}
            if apply:
                fid = self.s.add_fact(text, kind="fact", source="consolidate:day:" + days[0], source_kind="chat",
                                      importance=min(0.8, 0.3 + 0.05 * ndays), ts=self.clock(), actor="consolidate")
                for d in days[1:]:
                    self.s.lad_evidence(self.s.get_fact(fid)["ladder_id"], "consolidate:day:" + d, "chat", self.clock())
                rec["ref"] = "f:%d" % fid
                rec["level_name"] = self.s.get_fact(fid)["level_name"]
            res.append(rec)
        if apply:
            _commit(self.s)
        return res

    # ---------- конфликты ----------
    @staticmethod
    def _split_copula(text):
        m = re.match(r"^(.{3,80}?)\s*(?:—|-|:|\bэто\b|\bзовут\b|\bравен\b|\bравна\b)\s+(.{1,120})$", text.strip())
        return (norm_text(m.group(1)), norm_text(m.group(2))) if m else None

    def _conflict_kind(self, ta, tb):
        wa, wb = re.findall(r"[^\W_]+", ta.casefold()), re.findall(r"[^\W_]+", tb.casefold())
        na, nb = {w for w in wa if w.isdigit()}, {w for w in wb if w.isdigit()}
        ca, cb = [w for w in wa if w not in NEG and not w.isdigit()], [w for w in wb if w not in NEG and not w.isdigit()]
        if ca and ca == cb and (sum(w in NEG for w in wa) % 2) != (sum(w in NEG for w in wb) % 2):
            return "negation"
        sa, sb = set(ca), set(cb)
        if na and nb and na != nb and sa and sb and len(sa & sb) / len(sa | sb) >= 0.6:
            return "value"
        ka, kb = self._split_copula(ta), self._split_copula(tb)
        if ka and kb and ka[0] == kb[0] and ka[1] != kb[1] and not (set(stems(ka[1])) & set(stems(kb[1]))):
            return "value"
        return None

    def detect_conflicts(self, bucket_cap=60):
        buckets = defaultdict(list)
        for f in self.s.active_facts():
            st = stems(f["text"])
            if st:
                buckets[tuple(sorted(st[:2]))].append(f)
                if len(st) > 2:
                    buckets[tuple(sorted(st[:1] + st[2:3]))].append(f)
        pairs = {}
        for items in buckets.values():
            items = items[:bucket_cap]
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    a, b = items[i], items[j]
                    key = "|".join(sorted((a["ref"], b["ref"])))
                    if key in pairs:
                        continue
                    kind = self._conflict_kind(a["text"], b["text"])
                    if kind:
                        pairs[key] = {"kind": kind, "a": a, "b": b, "pair": key}
        return list(pairs.values())

    def _describe(self, f):
        bits = [f["level_name"]]
        if f["owner_confirmed"]:
            bits.append("подтверждено вами")
        bits.append("записано " + day_of(f["created"] or 0))
        return "«%s» (%s)" % (f["text"], ", ".join(bits))

    def ask_conflicts(self, apply=False):
        """Создать вопросы владельцу по новым конфликтам (не больше max_open открытых одновременно)."""
        open_n = self.s.db.execute("SELECT COUNT(*) FROM mem_questions WHERE status='open'").fetchone()[0]
        made = []
        for c in sorted(self.detect_conflicts(), key=lambda c: c["pair"]):
            if open_n + len(made) >= self.max_open:
                break
            if self.s.db.execute("SELECT 1 FROM mem_questions WHERE pair=?", (c["pair"],)).fetchone():
                continue
            q = ("Мессир, в памяти расходятся два утверждения. (1) %s. (2) %s. Какое верно? "
                 "Ответьте: 1, 2, оба или ни одно. Пока вы не ответили, я не принимаю ничью сторону." %
                 (self._describe(c["a"]), self._describe(c["b"])))
            item = {"kind": c["kind"], "a_ref": c["a"]["ref"], "b_ref": c["b"]["ref"], "pair": c["pair"], "question": q}
            if apply:
                cur = self.s.db.execute("INSERT INTO mem_questions(ts,kind,a_ref,b_ref,pair,question) VALUES(?,?,?,?,?,?)",
                                        (self.clock(), c["kind"], c["a"]["ref"], c["b"]["ref"], c["pair"], q))
                item["id"] = cur.lastrowid
            made.append(item)
        if apply:
            _commit(self.s)
        return made

    def open_questions(self):
        return [dict(zip(("id", "kind", "a_ref", "b_ref", "question", "ts"), r)) for r in self.s.db.execute(
            "SELECT id,kind,a_ref,b_ref,question,ts FROM mem_questions WHERE status='open' ORDER BY id")]

    def answer(self, qid, choice, actor="owner"):
        """choice: '1' | '2' | 'both' | 'neither'. Применяет решение через Corrector (чтение из S03 подтверждает)."""
        if self.c is None:
            raise ValueError("для ответа нужен Corrector")
        row = self.s.db.execute("SELECT a_ref,b_ref,status FROM mem_questions WHERE id=?", (qid,)).fetchone()
        if not row:
            return {"ok": False, "error": "нет вопроса %s" % qid}
        a, b, status = row
        if status != "open":
            return {"ok": False, "error": "вопрос уже закрыт"}
        choice = str(choice).strip().lower()
        why = "конфликт, вопрос %d: владелец выбрал %s" % (qid, choice)
        steps = []
        if choice == "1":
            steps = [self.c.confirm(a, actor), self.c.revoke(b, why, actor)]
        elif choice == "2":
            steps = [self.c.confirm(b, actor), self.c.revoke(a, why, actor)]
        elif choice in ("both", "оба"):
            steps = [self.c.confirm(a, actor), self.c.confirm(b, actor)]
        elif choice in ("neither", "ни одно"):
            steps = [self.c.revoke(a, why, actor), self.c.revoke(b, why, actor)]
        else:
            return {"ok": False, "error": "ответ: 1, 2, both или neither"}
        ok = all(s.get("ok") for s in steps)
        if ok:
            self.s.db.execute("UPDATE mem_questions SET status='answered', answer=?, answered_ts=? WHERE id=?",
                              (choice, self.clock(), qid))
            _commit(self.s)
        return {"ok": ok, "steps": steps}

    # ---------- общий прогон ----------
    def run(self, apply=False):
        rep = {"applied": bool(apply)}
        rep["episodes"] = self.consolidate_episodes(apply)
        rep["beliefs"] = self.beliefs(apply)
        rep["forget"] = self.forget(apply)
        rep["questions"] = self.ask_conflicts(apply)
        return rep


if __name__ == "__main__":  # python3 consolidate.py /root/nox/state/s03.sqlite [--apply]
    import sys
    from qs6.s03_store import Store
    from correction import Corrector
    st = Store(sys.argv[1])
    print(json.dumps(Consolidator(st, Corrector(st)).run("--apply" in sys.argv), ensure_ascii=False, indent=1, default=str))
