"""correction: правка и отзыв памяти владельцем С ПОДТВЕРЖДЕНИЕМ чтением из S03 и инвалидацией recall.

Что исправляет по сравнению с qs6/recall_api.py (который остаётся исполнителем операций):
  1. «ok:true» не считается доказательством: после правки/отзыва запись читается ЗАНОВО (новое соединение к файлу
     базы - видно только закоммиченное) и сверяется; при расхождении правка откатывается, ответ ok:false.
  2. Инвалидация recall проверяется: нет вектора (mem_vectors), FTS-строка = новый текст (или нет вообще),
     в блоке ядра отозванного нет, поиск по старому тексту его не возвращает, revision S03 сменился.
  3. Отозванное не воскресает: таблица mem_revoked + guarded_add_fact(); лестница Riverse хранит свидетельства
     по ключу текста, поэтому без этого повторная реплика владельца вернула бы факт на прежний уровень.
  4. Следы: эпизоды, дословно содержащие отозванный текст, находятся (traces) и по желанию архивируются.
CorrectionAPI(recall) - обёртка над Recall.handle: добавляет op get/revoke/restore/revision, остальное делегирует.
"""
import hashlib
import json
import re
import time

from memcommon import commit as _commit, day_of, ensure_schema, fresh_connection, norm_text

try:  # SECRET_RE из хранилища, если репозиторий доступен; иначе та же логика локально
    from qs6.s03_store import SECRET_RE
except Exception:  # pragma: no cover - зависит от окружения
    SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
                           r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:password|passwd|пароль|token|токен|api[_-]?key|secret)\s*[:=]\s*\S{6,})", re.I)

_TABLE = {"f": ("mem_facts", "id"), "e": ("mem_episodes", "id"), "p": ("mem_profile", "key")}


def _split(ref):
    p, _, i = str(ref).partition(":")
    if p not in _TABLE or not i:
        raise ValueError("неверный id воспоминания: %r" % (ref,))
    return p, (i if p == "p" else int(i))


def revoked_key(store, ref=None, text=None):
    """Ключ отзыва: нормализованный текст (для профиля - 'p:<ключ>')."""
    if ref and str(ref).startswith("p:"):
        return "p:" + str(ref)[2:]
    return norm_text(text)


def is_revoked(store, text=None, ref=None):
    ensure_schema(store)
    r = store.db.execute("SELECT 1 FROM mem_revoked WHERE key=? AND active=1", (revoked_key(store, ref, text),)).fetchone()
    return bool(r)


def guarded_add_fact(store, text, **kw):
    """store.add_fact, но отозванное/заменённое владельцем не добавляется заново. -> id | None (заблокировано)."""
    if is_revoked(store, text):
        store._log(kw.get("actor", "system"), "blocked_revoked", None, None, text, "повтор отозванного факта")
        _commit(store)
        return None
    return store.add_fact(text, **kw)


def revision(store):
    """Хэш активного содержимого S03 (64 hex, формат nox_hot_context.s03_revision): меняется при любой правке/отзыве."""
    h = hashlib.sha256()
    db = store.db
    for r in db.execute("SELECT id,text FROM mem_facts WHERE status='active' ORDER BY id"):
        h.update(("f%d|%s\n" % r).encode())
    for r in db.execute("SELECT key,value FROM mem_profile WHERE status='active' ORDER BY key"):
        h.update(("p%s|%s\n" % r).encode())
    h.update(str(db.execute("SELECT COALESCE(MAX(id),0) FROM mem_changes").fetchone()[0]).encode())
    return h.hexdigest()


class Corrector:
    def __init__(self, store, recall=None, clock=time.time):
        ensure_schema(store)
        self.s = store
        self.clock = clock
        if recall is None:
            from qs6.memory_search import MemorySearch
            from qs6.recall_api import Recall
            recall = Recall(store, MemorySearch(store, use_env_embedder=False))
        self.recall = recall

    # --- чтение из S03 (минуя кэши объекта) ---
    def readback(self, ref):
        """Свежее чтение записи: {id,type,text,status}|None. Для файловой базы - отдельное соединение."""
        p, ident = _split(ref)
        table, col = _TABLE[p]
        cols = "key,value,status" if p == "p" else "id,text,status"
        db, close = fresh_connection(self.s)
        try:
            r = db.execute("SELECT %s FROM %s WHERE %s=?" % (cols, table, col), (ident,)).fetchone()
        finally:
            if close:
                db.close()
        if not r:
            return None
        text = r[1] if p == "f" or p == "e" else "%s: %s" % (r[0], r[1])
        return {"id": ref, "type": {"f": "fact", "e": "episode", "p": "profile"}[p],
                "text": r[1] if p != "p" else r[1], "display": text, "status": r[2]}

    def get(self, ref):
        rb = self.readback(ref)
        if rb is None:
            raise KeyError("нет такой записи: %s" % ref)
        return rb

    # --- проверки инвалидации ---
    def _fts_body(self, ref):
        if not self.s.fts:
            return "n/a"
        r = self.s.db.execute("SELECT body FROM mem_fts WHERE ref=?", (ref,)).fetchone()
        return r[0] if r else None

    def _has_vector(self, ref):
        return self.s.db.execute("SELECT 1 FROM mem_vectors WHERE ref=?", (ref,)).fetchone() is not None

    def verify_absent(self, ref, old_text):
        """Отозванное не должно попадать в recall: ядро, поиск, FTS, вектор. + следы в эпизодах (не провал)."""
        from qs6.core_block import build_core_block
        core_items = build_core_block(self.s, budget_tokens=4000)["items"]
        hits = self.recall.search.search(old_text, k=20)["hits"]
        checks = {"core": ref not in core_items, "search": all(h["ref"] != ref for h in hits),
                  "fts": self._fts_body(ref) in (None, "n/a"), "vector": not self._has_vector(ref)}
        return checks, self.traces(old_text, exclude=ref)

    def traces(self, text, exclude=None):
        """Активные эпизоды, дословно содержащие текст (нормализованный): через них отозванное могло бы вернуться."""
        key = norm_text(text)
        if len(key) < 6:
            return []
        out = []
        for i, t in self.s.db.execute("SELECT id,text FROM mem_episodes WHERE status='active'"):
            if key in norm_text(t) and "e:%d" % i != exclude:
                out.append("e:%d" % i)
        return out

    def _record(self, ref, op, old, new, verified, detail):
        self.s.db.execute("INSERT INTO mem_corrections(ts,ref,op,old,new,verified,detail) VALUES(?,?,?,?,?,?,?)",
                          (self.clock(), ref, op, old, new, int(bool(verified)), json.dumps(detail, ensure_ascii=False)))
        _commit(self.s)

    def _mark_revoked(self, key, ref, actor, reason, change_id):
        self.s.db.execute("INSERT INTO mem_revoked(key,ref,ts,actor,reason,change_id,active) VALUES(?,?,?,?,?,?,1) "
                          "ON CONFLICT(key) DO UPDATE SET ref=excluded.ref, ts=excluded.ts, actor=excluded.actor, "
                          "reason=excluded.reason, change_id=excluded.change_id, active=1",
                          (key, ref, self.clock(), actor, reason, change_id))
        _commit(self.s)

    # --- операции ---
    def confirm(self, ref, actor="owner"):
        self.recall.confirm(ref, actor)
        rb = self.readback(ref)
        if rb is None or rb["status"] != "active":
            return {"ok": False, "error": "подтверждение не видно в S03"}
        flag = self._owner_flag(ref)
        return {"ok": bool(flag is None or flag), "verified": True, "readback": rb, "owner_confirmed": flag}

    def _owner_flag(self, ref):
        p, ident = _split(ref)
        if p == "p":
            return None
        table = _TABLE[p][0]
        db, close = fresh_connection(self.s)
        try:
            r = db.execute("SELECT owner_confirmed FROM %s WHERE id=?" % table, (ident,)).fetchone()
        finally:
            if close:
                db.close()
        return bool(r[0]) if r else None

    def correct(self, ref, new_text, reason=None, actor="owner"):
        """Правка с подтверждением. -> {ok, verified, error?, old, new, readback, invalidated, revision}."""
        new_text = (new_text or "").strip()
        try:
            if not new_text:
                raise ValueError("пустой текст исправления")
            if SECRET_RE.search(new_text):
                raise ValueError("в тексте похоже на секрет (ключ/пароль): в память не пишу")
            before = self.readback(ref)
            if before is None or before["status"] != "active":
                raise KeyError("нет активной записи: %s" % ref)
            old = before["text"]
            rev0 = revision(self.s)
            self.recall.correct(ref, new_text, actor, reason)
        except KeyError as e:
            return {"ok": False, "verified": False, "error": "нет поля/записи: %s" % e}
        except ValueError as e:
            return {"ok": False, "verified": False, "error": str(e)}
        rb = self.readback(ref)
        inv = {"vector_dropped": not self._has_vector(ref), "fts_current": self._fts_body(ref) in ("n/a",) or
               (self._fts_body(ref) or "").endswith(new_text),
               "revision_changed": revision(self.s) != rev0}
        persisted = bool(rb and rb["status"] == "active" and rb["text"] == new_text)
        if not (persisted and inv["vector_dropped"] and inv["fts_current"]):
            self._restore_text(ref, old, actor)
            self._record(ref, "correct", old, new_text, False, {"persisted": persisted, "inv": inv})
            return {"ok": False, "verified": False, "error": "S03 не подтвердил правку, запись возвращена к прежнему тексту",
                    "old": old, "new": new_text, "invalidated": inv}
        if norm_text(old) != norm_text(new_text):
            self._mark_revoked(norm_text(old), ref, actor, "заменено правкой: " + (reason or ""), None)
        self._record(ref, "correct", old, new_text, True, {"inv": inv})
        return {"ok": True, "verified": True, "old": old, "new": new_text, "readback": rb, "invalidated": inv,
                "revision": revision(self.s)}

    def _restore_text(self, ref, old, actor):
        try:
            self.recall.correct(ref, old, actor, "автооткат: правка не подтверждена чтением из S03")
        except Exception:
            pass

    def revoke(self, ref, reason=None, actor="owner", cascade_episodes=False):
        """Отзыв (мягкое удаление) + проверка, что recall его больше не отдаёт. -> {ok, verified, checks, traces, change_id}."""
        try:
            before = self.readback(ref)
            if before is None or before["status"] != "active":
                raise KeyError("нет активной записи: %s" % ref)
            old = before["text"] if before["type"] != "profile" else before["display"]
            rev0 = revision(self.s)
            res = self.recall.delete(ref, actor, reason)
        except KeyError as e:
            return {"ok": False, "verified": False, "error": "нет поля/записи: %s" % e}
        except ValueError as e:
            return {"ok": False, "verified": False, "error": str(e)}
        key = revoked_key(self.s, ref, old)
        self._mark_revoked(key, ref, actor, reason or "", res.get("change_id"))
        if ref.startswith("f:"):   # понизить уверенность в лестнице: без этого вернулся бы на старый уровень
            lid = self.s.db.execute("SELECT ladder_id FROM mem_facts WHERE id=?", (int(ref[2:]),)).fetchone()
            if lid and lid[0]:
                self.s.ladder.contradict(lid[0], "owner:revoke", "owner", self.clock())
        rb = self.readback(ref)
        checks, traces = self.verify_absent(ref, old)
        checks["status_deleted"] = bool(rb and rb["status"] == "deleted")
        checks["revision_changed"] = revision(self.s) != rev0
        archived = []
        if cascade_episodes and traces:
            archived = self._archive_episodes(traces, actor, "след отозванного " + ref)
            traces = [t for t in traces if t not in archived]
        verified = all(checks.values())
        self._record(ref, "revoke", old, None, verified, {"checks": checks, "traces": traces, "archived": archived})
        return {"ok": verified, "verified": verified, "ref": ref, "change_id": res.get("change_id"), "checks": checks,
                "traces": traces, "archived_traces": archived, "revision": revision(self.s),
                **({} if verified else {"error": "отзыв не подтверждён чтением: %s" % [k for k, v in checks.items() if not v]})}

    def _archive_episodes(self, refs, actor, reason):
        done = []
        for r in refs:
            i = int(r[2:])
            self.s.db.execute("UPDATE mem_episodes SET status='deleted' WHERE id=? AND status='active'", (i,))
            self.s._fts_set(r, None)
            self.s.db.execute("DELETE FROM mem_vectors WHERE ref=?", (r,))
            self.s._log(actor, "delete", r, None, None, reason)
            done.append(r)
        _commit(self.s)
        return done

    def restore(self, change_id, actor="owner"):
        """Откат отзыва/правки (Recall.revert) + снятие метки отзыва, чтобы факт снова мог жить."""
        row = self.s.db.execute("SELECT action,ref FROM mem_changes WHERE id=?", (change_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "нет записи журнала %s" % change_id}
        try:
            rec = self.recall.revert(change_id, actor)
        except (KeyError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        if row[0] == "delete":
            self.s.db.execute("UPDATE mem_revoked SET active=0 WHERE ref=?", (row[1],))
        _commit(self.s)
        rb = self.readback(row[1])
        return {"ok": bool(rb and rb["status"] == "active"), "readback": rb, "revision": revision(self.s)}


class CorrectionAPI:
    """Обёртка над Recall.handle: тот же JSON-протокол + get/revoke/restore/revision; delete -> revoke с проверкой."""

    def __init__(self, recall):
        self.recall = recall
        self.s = recall.s          # recall_api.serve() обращается к recall.s.stats()
        self.c = Corrector(recall.s, recall)

    def handle(self, req):
        op = req.get("op")
        try:
            if op == "get":
                rb = self.c.get(req["id"])
                return {"ok": True, "item": {"id": rb["id"], "text": rb["text"], "status": rb["status"], "type": rb["type"]}}
            if op == "correct":
                r = self.c.correct(req["id"], req["text"], req.get("reason"), req.get("actor", "owner"))
                if r["ok"]:
                    r["item"] = {"id": req["id"], "text": r["new"], "status": "active"}
                return r
            if op in ("delete", "revoke"):
                return self.c.revoke(req["id"], req.get("reason"), req.get("actor", "owner"), bool(req.get("cascade_episodes")))
            if op == "restore":
                return self.c.restore(int(req["change_id"]), req.get("actor", "owner"))
            if op == "revision":
                return {"ok": True, "revision": revision(self.recall.s)}
        except KeyError as e:
            return {"ok": False, "error": "нет поля/записи: %s" % e}
        except (ValueError, TypeError) as e:
            return {"ok": False, "error": str(e)}
        return self.recall.handle(req)
