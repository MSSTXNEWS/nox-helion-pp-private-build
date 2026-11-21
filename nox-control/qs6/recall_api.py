"""recall_api: «Что NOX вспомнил» (D05-12) и правка памяти владельцем.

Recall.recall_for_reply() ищет по памяти, собирает блок ядра, ЗАПИСЫВАЕТ какие воспоминания пошли в ответ
(таблица mem_usage). remembered(turn_id) возвращает их списком с id. Исправить/удалить/подтвердить
пишутся в журнал mem_changes; удаление мягкое (status=deleted), его можно откатить revert().
handle(dict) - JSON-API для веба; serve() - минимальный HTTP-сервер на 127.0.0.1 (описание в README_QS6B.md).
"""
import json
import sqlite3
import time
import uuid

from .core_block import build_core_block
from .memory_search import MemorySearch
from .s03_store import LEVELS, norm_text, ref_of, split_ref


class Recall:
    def __init__(self, store, search=None, bus=None):
        self.s = store
        self.search = search or MemorySearch(store)
        self.bus = bus

    def _emit(self, typ, data):
        if self.bus is not None:
            try:
                self.bus.publish(typ, data, source="recall")
            except Exception:
                pass

    # --- использование в ответе ---
    def mark_used(self, turn_id, refs, via="search", query="", scores=None, ts=None):
        ts = ts or time.time()
        for r in refs:
            self.s.db.execute("INSERT INTO mem_usage(turn_id,ref,ts,score,query,via) VALUES(?,?,?,?,?,?)",
                              (turn_id, r, ts, (scores or {}).get(r), query, via))
            self.s.touch(r, ts)
        self.s.db.commit()

    def recall_for_reply(self, query, turn_id=None, k=6, budget_tokens=400, kinds=None):
        turn_id = turn_id or uuid.uuid4().hex[:12]
        core = build_core_block(self.s, budget_tokens=budget_tokens)
        res = self.search.search(query, k=k, kinds=kinds)
        core_refs = set(core["items"])
        hits = [h for h in res["hits"] if h["ref"] not in core_refs]
        self.mark_used(turn_id, core["items"], "core", query)
        self.mark_used(turn_id, [h["ref"] for h in hits], "search", query, {h["ref"]: h["score"] for h in hits})
        self._emit("memory.found", {"turn_id": turn_id, "query": query, "core": len(core["items"]),
                                    "found": len(hits), "refs": [h["ref"] for h in hits], "mode": res["mode"]})
        return {"turn_id": turn_id, "core": core, "search": dict(res, hits=hits)}

    def remembered(self, turn_id):
        """Список использованных в ответе воспоминаний: [{id,type,text,via,level,...,actions}]."""
        rows = self.s.db.execute("SELECT ref,via,score,ts FROM mem_usage WHERE turn_id=? ORDER BY id", (turn_id,)).fetchall()
        items, seen = [], set()
        for ref, via, score, ts in rows:
            if ref in seen:
                continue
            seen.add(ref)
            rec = self.s.get(ref)
            if rec is None:
                items.append({"id": ref, "available": False, "via": via, "note": "запись удалена или не найдена"})
                continue
            if rec.get("status", "active") != "active":
                items.append({"id": ref, "available": False, "via": via, "note": "запись удалена владельцем"})
                continue
            it = {"id": ref, "type": rec["type"], "text": self.s.text_of(rec), "via": via, "score": score,
                  "used_at": ts, "available": True, "actions": ["confirm", "correct", "delete"]}
            if rec["type"] == "fact":
                it.update(level=rec["level"], level_name=rec["level_name"], kind=rec["kind"],
                          owner_confirmed=bool(rec["owner_confirmed"]), source=rec["source"], created=rec["created"])
            elif rec["type"] == "episode":
                it.update(source=rec["source"], created=rec["ts"], owner_confirmed=bool(rec["owner_confirmed"]))
            else:
                it.update(source=rec["source"], created=rec["updated"], section=rec["section"])
            items.append(it)
        return {"turn_id": turn_id, "items": items, "count": len(items)}

    # --- правка ---
    def _active(self, ref):
        rec = self.s.get(ref)
        if rec is None:
            raise KeyError("нет такой записи: %s" % ref)
        if rec.get("status", "active") != "active":
            raise ValueError("запись уже удалена: %s" % ref)
        return rec

    def confirm(self, ref, actor="owner"):
        rec = self._active(ref)
        db = self.s.db
        if rec["type"] == "fact":
            db.execute("UPDATE mem_facts SET owner_confirmed=1, updated=? WHERE id=?", (time.time(), rec["id"]))
            self.s.ladder.add_evidence(rec["ladder_id"], "owner:confirm", "owner", time.time())
        elif rec["type"] == "episode":
            db.execute("UPDATE mem_episodes SET owner_confirmed=1 WHERE id=?", (rec["id"],))
        self.s._log(actor, "confirm", ref, None, None, None)
        db.commit()
        self._emit("memory.changed", {"ref": ref, "action": "confirm"})
        return self.s.get(ref)

    def correct(self, ref, new_text, actor="owner", reason=None):
        new_text = (new_text or "").strip()
        if not new_text:
            raise ValueError("пустой текст исправления")
        rec = self._active(ref)
        db, now = self.s.db, time.time()
        old = self.s.text_of(rec) if rec["type"] != "profile" else rec["value"]
        if rec["type"] == "fact":
            key = norm_text(new_text)
            dup = db.execute("SELECT id FROM mem_facts WHERE key=? AND status='active' AND id<>?", (key, rec["id"])).fetchone()
            if dup:
                raise ValueError("такой факт уже есть: %s" % ref_of("fact", dup[0]))
            db.execute("UPDATE mem_facts SET text=?, key=?, updated=?, owner_confirmed=1 WHERE id=?", (new_text, key, now, rec["id"]))
            try:
                db.execute("UPDATE facts SET text=?, key=?, updated=? WHERE id=?", (new_text, key, now, rec["ladder_id"]))
            except sqlite3.IntegrityError:
                db.rollback()
                raise ValueError("такой текст уже есть в лестнице уверенности")
            self.s._fts_set(ref, new_text)
        elif rec["type"] == "episode":
            db.execute("UPDATE mem_episodes SET text=?, owner_confirmed=1 WHERE id=?", (new_text, rec["id"]))
            self.s._fts_set(ref, new_text)
        else:
            db.execute("UPDATE mem_profile SET value=?, source=?, updated=? WHERE key=?", (new_text, actor, now, rec["key"]))
            self.s._fts_set(ref, rec["key"] + ": " + new_text)
        db.execute("DELETE FROM mem_vectors WHERE ref=?", (ref,))
        self.s._log(actor, "correct", ref, old, new_text, reason)
        db.commit()
        self._emit("memory.changed", {"ref": ref, "action": "correct"})
        return self.s.get(ref)

    def delete(self, ref, actor="owner", reason=None):
        rec = self._active(ref)
        db = self.s.db
        old = rec["value"] if rec["type"] == "profile" else rec["text"]
        table, col, val = {"fact": ("mem_facts", "id", rec.get("id")), "episode": ("mem_episodes", "id", rec.get("id")),
                           "profile": ("mem_profile", "key", rec.get("key"))}[rec["type"]]
        db.execute("UPDATE %s SET status='deleted' WHERE %s=?" % (table, col), (val,))
        self.s._fts_set(ref, None)
        db.execute("DELETE FROM mem_vectors WHERE ref=?", (ref,))
        cid = self.s._log(actor, "delete", ref, old, None, reason)
        db.commit()
        self._emit("memory.changed", {"ref": ref, "action": "delete"})
        return {"ref": ref, "deleted": True, "change_id": cid}

    def revert(self, change_id, actor="owner"):
        r = self.s.db.execute("SELECT action,ref,old FROM mem_changes WHERE id=?", (change_id,)).fetchone()
        if not r:
            raise KeyError("нет записи журнала %s" % change_id)
        action, ref, old = r
        kind, ident = split_ref(ref)
        db = self.s.db
        if action == "delete":
            table, col = {"fact": ("mem_facts", "id"), "episode": ("mem_episodes", "id"), "profile": ("mem_profile", "key")}[kind]
            if kind == "fact" and db.execute("SELECT 1 FROM mem_facts WHERE status='active' AND key=(SELECT key FROM mem_facts WHERE id=?)", (ident,)).fetchone():
                raise ValueError("такая запись уже есть активной")
            db.execute("UPDATE %s SET status='active' WHERE %s=?" % (table, col), (ident,))
            rec = self.s.get(ref)
            self.s._fts_set(ref, self.s.text_of(rec))
            self.s._log(actor, "revert", ref, None, old, "откат изменения %d" % change_id)
            db.commit()
            return rec
        if action == "correct":
            out = self.correct(ref, old, actor, "откат изменения %d" % change_id)
            return out
        raise ValueError("откатить можно только delete/correct (в журнале: %s)" % action)

    def journal(self, limit=50, ref=None):
        q, a = "SELECT id,ts,actor,action,ref,old,new,reason FROM mem_changes", []
        if ref:
            q += " WHERE ref=?"; a.append(ref)
        rows = self.s.db.execute(q + " ORDER BY id DESC LIMIT ?", a + [int(limit)]).fetchall()
        return [dict(zip(("id", "ts", "actor", "action", "ref", "old", "new", "reason"), r)) for r in rows]

    # --- JSON-API ---
    def handle(self, req):
        """{"op": ..., ...} -> {"ok": true, ...} | {"ok": false, "error": "..."}"""
        try:
            op = req.get("op")
            if op == "recall":
                return {"ok": True, **self.recall_for_reply(req.get("query", ""), req.get("turn_id"), int(req.get("k", 6)),
                                                            int(req.get("budget_tokens", 400)))}
            if op == "remembered":
                return {"ok": True, **self.remembered(req["turn_id"])}
            if op == "confirm":
                return {"ok": True, "item": self.confirm(req["id"], req.get("actor", "owner"))}
            if op == "correct":
                return {"ok": True, "item": self.correct(req["id"], req["text"], req.get("actor", "owner"), req.get("reason"))}
            if op == "delete":
                return {"ok": True, **self.delete(req["id"], req.get("actor", "owner"), req.get("reason"))}
            if op == "revert":
                return {"ok": True, "item": self.revert(int(req["change_id"]), req.get("actor", "owner"))}
            if op == "journal":
                return {"ok": True, "changes": self.journal(int(req.get("limit", 50)), req.get("id"))}
            if op == "search":
                return {"ok": True, **self.search.search(req.get("query", ""), int(req.get("k", 8)))}
            if op == "core":
                return {"ok": True, **build_core_block(self.s, int(req.get("budget_tokens", 400)))}
            return {"ok": False, "error": "неизвестная операция: %r" % (op,)}
        except KeyError as e:
            return {"ok": False, "error": "нет поля/записи: %s" % e}
        except (ValueError, TypeError) as e:
            return {"ok": False, "error": str(e)}


def serve(recall, host="127.0.0.1", port=8788):
    """Минимальный HTTP: POST /api (тело - JSON-запрос handle), GET /health. Однопоточный доступ к SQLite."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._send(200 if self.path == "/health" else 404, {"ok": self.path == "/health", "stats": recall.s.stats()} if self.path == "/health" else {"ok": False})

        def do_POST(self):
            if self.path != "/api":
                return self._send(404, {"ok": False, "error": "POST /api"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                req = json.loads(self.rfile.read(min(n, 1 << 20)).decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("ожидался JSON-объект")
            except ValueError as e:
                return self._send(400, {"ok": False, "error": "плохой JSON: %s" % e})
            with lock:
                self._send(200, recall.handle(req))

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer((host, port), H)
    return srv
