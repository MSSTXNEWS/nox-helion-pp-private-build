"""gateway_prime: врезка единого режима NOX Prime в glm53/gateway.py (флаг NOX_PRIME=1).

Шлюз остаётся прежним (роутер тиров, двухтактный стрим, STOP, after_reply памяти). Меняется только сборка запроса:
  body["nox_system"] = статичная часть Prime (душа v3 + подпись характера) — неизменна между ходами -> KV-кэш жив;
  последнее user-сообщение = <внутреннее_состояние>(Я сейчас, взгляды, история, память) + исходный вопрос.
Органы подключаются по наличию модулей (каталог NOX_WOW7, по умолчанию /root/nox/src/wow7); нет модуля — орган пропущен.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _try(fn, log, what):
    try:
        return fn()
    except Exception as ex:
        log("[prime] %s не подключён: %s" % (what, ex))
        return None


def make_prime(mem=None, root=None, state=None, log=None):
    """Собирает Prime из органов v7. mem — qs6.MemoryLayer шлюза (для памяти S03)."""
    log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    root = root or os.environ.get("NOX_WOW7", "/root/nox/src/wow7")
    state = state or os.environ.get("NOX_STATE", "/root/nox/state")
    for d in ("PRIME", "CON", "PER", "EMO", "WORLD", "CTX"):
        p = os.path.join(root, d)
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    sys.path.insert(0, HERE)
    from nox_prime import Prime
    parts = {}
    per = _try(lambda: __import__("personality").Personality(path=os.path.join(state, "personality.json")), log, "личность")
    if per:
        parts["signature"] = per.signature
    aff = _try(lambda: __import__("affect_loop").Affect(state_dir=state), log, "эмоции")
    if aff:
        parts["affect"] = aff
        if per:
            _try(lambda: per.apply_to(aff.pad), log, "темперамент->PAD")
    ws = _try(lambda: __import__("nox_workspace").Workspace(), log, "рабочее пространство")
    if ws:
        parts["workspace"] = ws
    sm = _try(lambda: __import__("nox_self_model_live").LiveSelfModel(path=os.path.join(state, "self_live.json")), log, "я-модель")
    if sm:
        parts["self_model"] = sm
    bel = _try(lambda: __import__("beliefs").Beliefs(path=os.path.join(state, "beliefs.json")), log, "взгляды")
    if bel:
        parts["beliefs"] = bel
    dev = _try(lambda: __import__("development").Development(path=os.path.join(state, "development.json")), log, "развитие")
    if dev:
        parts["narrative"] = dev.narrative
    atlas_path = os.path.join(state, "self_atlas.txt")
    parts["atlas"] = lambda: open(atlas_path, encoding="utf-8").read()[:2500] if os.path.exists(atlas_path) else ""
    if mem is not None and getattr(mem, "recall", None) is not None:
        def memory(text, turn_id):
            with mem.lock:
                r = mem.recall.recall_for_reply(text, turn_id=turn_id, k=mem.k, budget_tokens=mem.core_budget)
            return {"core": r["core"]["text"], "recalled": [h["text"] for h in r["search"]["hits"]]}
        parts["memory"] = memory
    soul = os.environ.get("NOX_PRIME_SOUL", os.path.join(root, "PRIME", "soul_prime_v3.txt"))
    if not os.path.exists(soul):
        soul = os.path.join(HERE, "soul_prime_v3.txt")
    return Prime.from_file(soul, parts=parts, log=log)


def apply(prime, body, user, rid, info):
    """Заменяет _with_memory: возвращает новое тело запроса для существующего конвейера шлюза."""
    body = dict(body)
    body.pop("nox_system", None)
    msgs = list(body.get("messages") or [])
    hist = [m for m in msgs[:-1] if m.get("role") in ("user", "assistant")]
    r = prime.build(user, hist, rid)
    body["nox_system"] = r["messages"][0]["content"]
    if msgs and msgs[-1].get("role") == "user":
        msgs[-1] = dict(msgs[-1], content=r["messages"][-1]["content"])
    body["messages"] = msgs
    info["prime"] = {"route": r["route"], "static_hash": r["static_hash"], "dyn_chars": r["info"]["dyn_chars"],
                     "errors": r["info"]["errors"]}
    return body


PATCH = '''
--- a/nox-control/glm53/gateway.py
+++ b/nox-control/glm53/gateway.py
@@ class State.__init__
-        self.cfg = cfg; self.mem = ...
+        self.cfg = cfg; self.mem = ...   (без изменений)
+        self.prime = None
+        if os.environ.get("NOX_PRIME") == "1":
+            try:
+                import gateway_prime as GP; self.prime = GP.make_prime(self.mem)
+            except Exception as e: print("[prime] выключен: %s" % e, file=sys.stderr, flush=True)
@@ def _with_memory(self, body, user, rid, info, plan):
             body = dict(body); body.pop("nox_system", None)
+            if st.prime is not None:
+                try: return GP_apply(st.prime, body, user, rid, info)
+                except Exception as e: info["prime_error"] = str(e)   # падение Prime -> старая душа qs6
             if not st.mem: return body
@@ после mem.after_reply(...)
+                        if st.prime is not None: st.prime.after_reply(user, self._res["text"], rid)
'''
