"""task_runner (ACT-01): обратимые задачи NOX с журналом, идемпотентностью и честной квитанцией.

Карточка задачи (JSON):
  {"id":"T1","title":"...","steps":[{"id":"s1","op":"write_file","args":{...},"verify":[{...}]}],
   "verify":[{...}],            # итоговая проверка карточки
   "on_fail":"rollback"|"keep", # по умолчанию rollback
   "retries":1}                 # повторы шага при OSError (временная ошибка)
Операции — закрытый набор ОБРАТИМЫХ файловых изменений внутри рабочей папки (ws):
  write_file, patch_file, append_line, json_set, json_upsert, board_add, calendar_add.
Необратимых операций (сеть, удаление, запуск побочных команд) здесь нет намеренно.
Проверки (verify): file_exists, file_absent, file_contains, file_not_contains, file_sha, json_eq,
  json_has_item, cmd_ok (python3/bash/sh, rlimit, без сети если есть unshare).

Идемпотентность: ключ = sha256(канон. карточки)[:16]; повторная отправка = та же задача, не дубль.
Журнал событий (JSONL, цепочка хешей, fsync) — источник правды; состояние = replay журнала.
Outbox-порядок: intent(+снимок «до») -> эффект -> applied -> verify -> done. После обрыва шаг с intent без applied
повторяется: операции идемпотентны по состоянию (no-op, если эффект уже есть), снимок «до» берётся из ПЕРВОГО intent.
Откат: обратный порядок, восстановление «до», если файл всё ещё в состоянии «после»; чужую правку не затираем (conflict).
Квитанция: пишется из журнала И живой перепроверки состояния, не из слов модели.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import argparse
import base64
import fcntl
import hashlib
import json

import statefile
from quiet import in_quiet
import os
import re
import resource
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

MAX_FILE = 1 << 20
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
KANBAN = {"queued": "todo", "running": "doing", "done": "done", "failed": "blocked",
          "rolling_back": "doing", "rolled_back": "rolled_back", "rollback_conflict": "blocked"}
MSK = timezone(timedelta(hours=3))


class Crash(BaseException):
    """Имитация смерти процесса (тесты/приёмка). BaseException — чтобы не ловилась как ошибка шага."""


class ActError(Exception):
    pass


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def atomic_write(path, data):
    statefile.write_bytes(path, data, lock=False)   # атомарно (tmp+fsync+replace); .lock рядом с файлами задач не оставляем


# ---------------------------------------------------------------- журнал
class Journal:
    def __init__(self, path):
        self.path = path

    def read(self):
        if not os.path.exists(self.path):
            return []
        out, prev = [], ""
        with open(self.path, "rb") as f:
            raw = f.read()
        for line in raw.split(b"\n"):
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                break  # оборванная последняя запись
            body = {k: v for k, v in ev.items() if k != "h"}
            if ev.get("h") != sha_b((prev + canon(body)).encode()):
                raise ActError("journal hash chain broken at seq %s" % ev.get("seq"))
            prev = ev["h"]
            out.append(ev)
        return out

    def append(self, ev, events):
        """events — уже прочитанный список (для prev/seq); дописывает и возвращает событие."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._repair(events)
        prev = events[-1]["h"] if events else ""
        ev = dict(ev, seq=len(events) + 1, ts=round(time.time(), 3))
        ev["h"] = sha_b((prev + canon(ev)).encode())
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (canon(ev) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        events.append(ev)
        return ev

    def _repair(self, events):
        """Отрезать оборванный хвост (запись без \\n или битый JSON) перед дозаписью."""
        if not os.path.exists(self.path):
            return
        good = sum(len(canon(e).encode()) + 1 for e in events)
        if os.path.getsize(self.path) != good:
            with open(self.path, "r+b") as f:
                f.truncate(good)


# ---------------------------------------------------------------- файловые операции
def _safe(ws, p):
    if not isinstance(p, str) or not p or "\0" in p:
        raise ActError("bad path")
    root = os.path.realpath(ws)
    full = os.path.join(root, p) if not os.path.isabs(p) else p
    parent = os.path.realpath(os.path.dirname(full))
    res = os.path.join(parent, os.path.basename(full))
    if not (res == root or res.startswith(root + os.sep)):
        raise ActError("path outside workspace: %s" % p)
    if os.path.islink(res):
        raise ActError("symlink refused: %s" % p)
    return res


def _read(p):
    if not os.path.exists(p):
        return None
    if os.path.getsize(p) > MAX_FILE:
        raise ActError("file too large for reversible op: %s" % p)
    with open(p, "rb") as f:
        return f.read()


def _t_write(a, old):
    return a["content"].encode()


def _t_patch(a, old):
    if old is None:
        raise ActError("patch_file: file missing")
    t = old.decode()
    if a["new"] in t:
        return old  # уже применено
    if t.count(a["old"]) != 1:
        raise ActError("patch_file: 'old' occurs %d times (need exactly 1)" % t.count(a["old"]))
    return t.replace(a["old"], a["new"]).encode()


def _t_append(a, old):
    t = old.decode() if old else ""
    if a["line"] in t.split("\n"):
        return old
    if t and not t.endswith("\n"):
        t += "\n"
    return (t + a["line"] + "\n").encode()


def _setdots(d, key, val):
    ks = key.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
        if not isinstance(d, dict):
            raise ActError("json_set: %s is not an object" % k)
    d[ks[-1]] = val


def _t_jset(a, old):
    d = json.loads(old.decode()) if old else {}
    _setdots(d, a["key"], a["value"])
    return (json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode()


def _upsert(old, list_key, item, id_field="id"):
    d = json.loads(old.decode()) if old else {}
    lst = d.setdefault(list_key, [])
    for i, x in enumerate(lst):
        if x.get(id_field) == item.get(id_field):
            lst[i] = item
            break
    else:
        lst.append(item)
    return (json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode()


def _t_upsert(a, old):
    if not isinstance(a.get("item"), dict) or "id" not in a["item"]:
        raise ActError("json_upsert: item.id required")
    return _upsert(old, a["list_key"], a["item"])


def _t_board(a, old):
    it = dict(a["item"])
    if not it.get("id") or not it.get("title"):
        raise ActError("board_add: item.id and item.title required")
    it.setdefault("column", "todo")
    if it["column"] not in ("todo", "doing", "done", "blocked", "rolled_back"):
        raise ActError("board_add: bad column")
    return _upsert(old, "cards", it)


def quiet_hour(iso):
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        raise ActError("calendar_add: start needs timezone offset")
    return in_quiet(dt.timestamp())


def _t_cal(a, old):
    ev = dict(a["item"])
    for k in ("id", "title", "start"):
        if not ev.get(k):
            raise ActError("calendar_add: item.%s required" % k)
    if quiet_hour(ev["start"]) and not ev.get("quiet_ok"):
        raise ActError("calendar_add: start in quiet hours 23:00-08:00 MSK")
    return _upsert(old, "events", ev)


OPS = {
    "write_file": (_t_write, ("path", "content")),
    "patch_file": (_t_patch, ("path", "old", "new")),
    "append_line": (_t_append, ("path", "line")),
    "json_set": (_t_jset, ("path", "key", "value")),
    "json_upsert": (_t_upsert, ("path", "list_key", "item")),
    "board_add": (_t_board, ("path", "item")),
    "calendar_add": (_t_cal, ("path", "item")),
}


def snap(path):
    b = _read(path)
    return {"exists": b is not None, "sha": sha_b(b) if b is not None else None,
            "b64": base64.b64encode(b).decode() if b is not None else None}


def missing_dirs(ws, path):
    root, out, d = os.path.realpath(ws), [], os.path.dirname(path)
    while d != root and not os.path.exists(d):
        out.append(d)
        d = os.path.dirname(d)
    return out


def apply_op(ws, step):
    op, args = step["op"], step["args"]
    fn, need = OPS[op]
    for k in need:
        if k not in args:
            raise ActError("%s: arg '%s' required" % (op, k))
    p = _safe(ws, args["path"])
    old = _read(p)
    new = fn(args, old)
    changed = new != old
    if changed:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        atomic_write(p, new)
    return {"changed": changed, "post_sha": sha_b(new)}


def undo_op(ws, step, before, post_sha):
    p = _safe(ws, step["args"]["path"])
    cur = _read(p)
    cur_sha = sha_b(cur) if cur is not None else None
    if cur_sha == before["sha"]:
        return "already"
    if cur_sha != post_sha:
        return "conflict"
    if before["exists"]:
        atomic_write(p, base64.b64decode(before["b64"]))
    else:
        os.unlink(p)
        for d in before.get("dirs", []):  # от глубокой к верхней; только созданные нами и пустые
            try:
                os.rmdir(d)
            except OSError:
                pass
    return "restored"


# ---------------------------------------------------------------- проверки
def _safe_cmd_env(tmp):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": tmp, "LANG": "C.UTF-8"}


def run_check(ws, cmd, timeout=15):
    if not cmd or os.path.basename(cmd[0]) not in ("python3", "bash", "sh"):
        raise ActError("cmd_ok: only python3/bash/sh")
    exe = shutil.which(cmd[0])
    if not exe:
        raise ActError("cmd_ok: %s not installed" % cmd[0])
    argv = [exe] + list(cmd[1:])
    if shutil.which("unshare") and subprocess.run(["unshare", "-n", "true"], capture_output=True).returncode == 0:
        argv = ["unshare", "-n"] + argv

    def lim():
        resource.setrlimit(resource.RLIMIT_CPU, (timeout + 2, timeout + 2))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        except (ValueError, OSError):
            pass
    try:
        p = subprocess.run(argv, cwd=ws, env=_safe_cmd_env(ws), capture_output=True, text=True,
                           timeout=timeout, preexec_fn=lim)
    except subprocess.TimeoutExpired:
        return False, "timeout", ""
    return p.returncode == 0, "rc=%d %s" % (p.returncode, p.stderr[-300:]), p.stdout


def check(ws, v):
    k = v.get("kind")
    try:
        if k in ("file_exists", "file_absent", "file_contains", "file_not_contains", "file_sha", "json_eq", "json_has_item"):
            p = _safe(ws, v["path"])
            b = _read(p)
            if k == "file_exists":
                return b is not None, "exists" if b is not None else "missing"
            if k == "file_absent":
                return b is None, "absent" if b is None else "present"
            if b is None:
                return False, "file missing"
            if k == "file_contains":
                return v["text"] in b.decode(), "contains" if v["text"] in b.decode() else "text not found"
            if k == "file_not_contains":
                return v["text"] not in b.decode(), "not contains" if v["text"] not in b.decode() else "text present"
            if k == "file_sha":
                return sha_b(b) == v["sha256"], "sha " + sha_b(b)[:12]
            d = json.loads(b.decode())
            if k == "json_eq":
                for part in v["key"].split("."):
                    d = d[part]
                return d == v["value"], "value=%r" % (d,)
            items = d.get(v["list_key"], [])
            hit = [x for x in items if x.get("id") == v["id"]]
            if hit and "fields" in v:
                hit = [x for x in hit if all(x.get(a) == b2 for a, b2 in v["fields"].items())]
            return bool(hit), "found" if hit else "item not found"
        if k == "cmd_ok":
            ok, d, out = run_check(ws, v["cmd"], v.get("timeout", 15))
            if ok and "stdout_contains" in v and v["stdout_contains"] not in out:
                return False, "stdout lacks expected text"
            return ok, d
    except (KeyError, ValueError, ActError, TypeError) as e:
        return False, "%s: %s" % (type(e).__name__, e)
    return False, "unknown check kind: %r" % (k,)


def verify_all(ws, vs):
    res = []
    for v in vs or []:
        ok, d = check(ws, v)
        res.append({"check": v, "ok": ok, "detail": d})
    return res


# ---------------------------------------------------------------- состояние
def replay(events):
    st = {"id": None, "key": None, "title": None, "status": None, "card": None, "steps": {},
          "attempts": 0, "errors": [], "head": events[-1]["h"] if events else None, "n_events": len(events)}
    for e in events:
        t = e["t"]
        st["last_ts"] = e["ts"]
        if t == "submitted":
            st.update(id=e["card"]["id"], key=e["key"], title=e["card"].get("title"), card=e["card"], status="queued",
                      submitted=e["ts"])
            for s in e["card"]["steps"]:
                st["steps"][s["id"]] = {"status": "pending", "before": None, "post_sha": None, "applied": 0, "reconciled": False}
        elif t == "run_start":
            st["attempts"] += 1
            st["status"] = "running"
            st.setdefault("started", e["ts"])
        elif t == "intent":
            s = st["steps"][e["step"]]
            if s["before"] is None:
                s["before"] = e["before"]
            s["status"] = "intent"
        elif t == "applied":
            s = st["steps"][e["step"]]
            s["post_sha"] = e["post_sha"]
            s["applied"] += 1
            s["reconciled"] = s["reconciled"] or (not e["changed"] and s["before"] and s["before"]["sha"] != e["post_sha"])
            s["status"] = "applied"
        elif t == "verified":
            s = st["steps"][e["step"]]
            s["status"] = "done" if e["ok"] else "verify_failed"
        elif t == "step_failed":
            sf = st["steps"][e["step"]]
            sf["status"] = "failed"
            if sf["applied"] == 0:
                sf["before"] = None  # эффекта не было: при повторе снимок «до» нужно взять заново
            st["errors"].append({"step": e["step"], "error": e["error"]})
        elif t == "rollback_start":
            st["status"] = "rolling_back"
        elif t == "undo":
            st["steps"][e["step"]]["undo"] = e["result"]
            if e["result"] != "conflict":
                st["steps"][e["step"]]["status"] = "undone"
        elif t == "finished":
            st["status"] = e["status"]
            st["finished"] = e["ts"]
    return st


def validate_card(card):
    if not isinstance(card, dict) or not ID_RE.match(str(card.get("id", ""))):
        raise ActError("card.id must match %s" % ID_RE.pattern)
    steps = card.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ActError("card.steps must be a non-empty list")
    seen = set()
    for s in steps:
        if not ID_RE.match(str(s.get("id", ""))) or s["id"] in seen:
            raise ActError("step ids must be unique and match id pattern")
        seen.add(s["id"])
        if s.get("op") not in OPS:
            raise ActError("unknown/irreversible op: %r (allowed %s)" % (s.get("op"), sorted(OPS)))
        if not isinstance(s.get("args"), dict):
            raise ActError("step.args must be an object")
    if card.get("on_fail", "rollback") not in ("rollback", "keep"):
        raise ActError("on_fail must be rollback|keep")


def card_key(card):
    c = {k: v for k, v in card.items() if k != "idem_key"}
    return card.get("idem_key") or sha_b(canon(c).encode())[:16]


class Runner:
    def __init__(self, ws, home, dispatch_dir=None, receipts_dir=None):
        self.ws = os.path.realpath(ws)
        self.home = home
        self.dispatch_dir = dispatch_dir
        self.receipts_dir = receipts_dir or os.path.join(home, "receipts")
        os.makedirs(self.ws, exist_ok=True)
        os.makedirs(os.path.join(home, "journals"), exist_ok=True)

    # --- служебное
    def _j(self, tid):
        return Journal(os.path.join(self.home, "journals", tid + ".jsonl"))

    def _lock(self, name, block=True):
        f = open(os.path.join(self.home, name + ".lock"), "a")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if block else fcntl.LOCK_NB))
        except OSError:
            f.close()
            return None
        return f

    def state(self, tid):
        if not ID_RE.match(tid):
            raise ActError("bad task id")
        return replay(self._j(tid).read())

    def list_tasks(self):
        d = os.path.join(self.home, "journals")
        return [self.state(n[:-6]) for n in sorted(os.listdir(d)) if n.endswith(".jsonl")]

    def stale(self, minutes=60, now=None):
        """Задачи в running/rolling_back без движения журнала дольше N минут (обрыв процесса) — для часового инспектора."""
        now = now or time.time()
        return [s["id"] for s in self.list_tasks()
                if s["status"] in ("running", "rolling_back") and now - s["last_ts"] > minutes * 60]

    # --- submit (идемпотентно)
    def submit(self, card):
        validate_card(card)
        key = card_key(card)
        lk = self._lock("submit")
        try:
            idx_p = os.path.join(self.home, "keys.json")
            idx = jload(idx_p) if os.path.exists(idx_p) else {}
            if key in idx:
                st = self.state(idx[key])
                return {"ok": True, "dup": True, "id": idx[key], "key": key, "status": st["status"]}
            j = self._j(card["id"])
            ev = j.read()
            if ev:
                return {"ok": False, "error": "task id %s exists with different content" % card["id"]}
            j.append({"t": "submitted", "card": card, "key": key}, ev)
            idx[key] = card["id"]
            atomic_write(idx_p, json.dumps(idx, indent=1).encode())
            st = replay(ev)
            self._sync(st)
            return {"ok": True, "dup": False, "id": card["id"], "key": key, "status": "queued"}
        finally:
            lk.close()

    # --- run
    def run(self, tid, crash=None):
        """crash(step_id, point) может бросить Crash; точки: after_intent, after_effect, after_applied, after_done."""
        lk = self._lock("task_" + tid, block=False)
        if lk is None:
            return {"ok": False, "blocked": "task is running in another process", "id": tid}
        try:
            j = self._j(tid)
            ev = j.read()
            st = replay(ev)
            if not ev:
                return {"ok": False, "error": "no such task"}
            if st["status"] in ("done", "rolled_back", "rollback_conflict"):
                return self._result(st)
            if st["status"] == "rolling_back":
                return self._rollback_locked(tid, j, ev, crash)
            card = st["card"]
            hook = crash or (lambda s, p: None)
            j.append({"t": "run_start"}, ev)
            self._sync(replay(ev))
            for step in card["steps"]:
                s = replay(ev)["steps"][step["id"]]
                if s["status"] == "done":
                    continue
                err = self._do_step(j, ev, card, step, s, hook)
                if err:
                    j.append({"t": "step_failed", "step": step["id"], "error": err}, ev)
                    if card.get("on_fail", "rollback") == "rollback":
                        return self._rollback_locked(tid, j, ev, crash, reason=err)
                    j.append({"t": "finished", "status": "failed"}, ev)
                    return self._finish(replay(ev))
            fin = verify_all(self.ws, card.get("verify"))
            bad = [r for r in fin if not r["ok"]]
            if bad:
                err = "final verify failed: %s" % bad[0]["detail"]
                j.append({"t": "step_failed", "step": card["steps"][-1]["id"], "error": err}, ev)
                if card.get("on_fail", "rollback") == "rollback":
                    return self._rollback_locked(tid, j, ev, crash, reason=err)
                j.append({"t": "finished", "status": "failed"}, ev)
                return self._finish(replay(ev))
            j.append({"t": "finished", "status": "done"}, ev)
            return self._finish(replay(ev))
        finally:
            lk.close()

    def _do_step(self, j, ev, card, step, s, hook):
        sid = step["id"]
        if s["before"] is None:
            args = step["args"]
            try:
                p = _safe(self.ws, args["path"])
                before = snap(p)
                before["dirs"] = missing_dirs(self.ws, p)
            except (ActError, KeyError) as e:
                return str(e)
            j.append({"t": "intent", "step": sid, "op": step["op"], "before": before}, ev)
        hook(sid, "after_intent")
        tries = 1 + int(card.get("retries", 1))
        for i in range(tries):
            try:
                res = apply_op(self.ws, step)
                break
            except OSError as e:
                if i == tries - 1:
                    return "OSError: %s" % e
                time.sleep(0.05 * (i + 1))
            except ActError as e:
                return str(e)
        hook(sid, "after_effect")
        j.append({"t": "applied", "step": sid, **res}, ev)
        hook(sid, "after_applied")
        vr = verify_all(self.ws, step.get("verify"))
        bad = [r for r in vr if not r["ok"]]
        j.append({"t": "verified", "step": sid, "ok": not bad, "results": [(r["check"].get("kind"), r["ok"], r["detail"]) for r in vr]}, ev)
        if bad:
            return "verify failed at %s: %s" % (sid, bad[0]["detail"])
        hook(sid, "after_done")
        return None

    # --- rollback
    def rollback(self, tid, crash=None):
        lk = self._lock("task_" + tid, block=False)
        if lk is None:
            return {"ok": False, "blocked": "task is running in another process", "id": tid}
        try:
            j = self._j(tid)
            ev = j.read()
            if not ev:
                return {"ok": False, "error": "no such task"}
            return self._rollback_locked(tid, j, ev, crash)
        finally:
            lk.close()

    def _rollback_locked(self, tid, j, ev, crash=None, reason=None):
        st = replay(ev)
        if st["status"] in ("rolled_back", "rollback_conflict"):
            return self._result(st)
        if st["status"] != "rolling_back":
            j.append({"t": "rollback_start", "reason": reason or "requested"}, ev)
            self._sync(replay(ev))
        hook = crash or (lambda s, p: None)
        card = st["card"]
        conflict = False
        for step in reversed(card["steps"]):
            s = replay(ev)["steps"][step["id"]]
            if s["before"] is None or s.get("undo") in ("restored", "already"):
                continue
            if s["post_sha"] is None:
                # эффект мог примениться без журнала applied (обрыв между эффектом и записью): вычислим post идемпотентно
                try:
                    p = _safe(self.ws, step["args"]["path"])
                    cur = _read(p)
                    post = sha_b(cur) if cur is not None else None
                except ActError:
                    post = None
                s_post = post
            else:
                s_post = s["post_sha"]
            if s_post is None and not s["before"]["exists"]:
                r = "already"
            else:
                r = undo_op(self.ws, step, s["before"], s_post)
            hook(step["id"], "after_undo_effect")
            j.append({"t": "undo", "step": step["id"], "result": r}, ev)
            conflict = conflict or r == "conflict"
        status = "rollback_conflict" if any(v.get("undo") == "conflict" for v in replay(ev)["steps"].values()) else "rolled_back"
        j.append({"t": "finished", "status": status}, ev)
        return self._finish(replay(ev))

    # --- результаты
    def _result(self, st):
        return {"ok": st["status"] == "done", "id": st["id"], "status": st["status"], "errors": st["errors"]}

    def _finish(self, st):
        self._sync(st)
        rc = self.receipt(st["id"], write=True)
        r = self._result(st)
        r["receipt"] = rc["path"]
        r["verified"] = rc["live_verify"]["ok"]
        return r

    def receipt(self, tid, write=False):
        st = self.state(tid)
        card = st["card"]
        steps = []
        for s in card["steps"]:
            x = st["steps"][s["id"]]
            steps.append({"id": s["id"], "op": s["op"], "status": x["status"], "applied_records": x["applied"],
                          "reconciled_after_crash": bool(x["reconciled"]), "post_sha": x["post_sha"], "undo": x.get("undo")})
        checks = []
        if st["status"] == "done":
            checks = verify_all(self.ws, card.get("verify"))
            for s in card["steps"]:
                checks += verify_all(self.ws, s.get("verify"))
        elif st["status"] in ("rolled_back", "rollback_conflict"):
            seen = set()  # по каждому пути сверяем с «до» ПЕРВОГО шага, трогавшего путь
            for s in card["steps"]:
                x = st["steps"][s["id"]]
                if x["before"] is None or s["args"]["path"] in seen:
                    continue
                seen.add(s["args"]["path"])
                p = _safe(self.ws, s["args"]["path"])
                b = _read(p)
                cur = sha_b(b) if b is not None else None
                checks.append({"check": {"kind": "restored_to_before", "path": s["args"]["path"]},
                               "ok": cur == x["before"]["sha"], "detail": "sha now %s, before %s" % (cur and cur[:12], x["before"]["sha"] and x["before"]["sha"][:12])})
        rc = {"id": "ACT-task-" + tid, "task_id": tid, "title": st["title"], "idem_key": st["key"], "status": st["status"],
              "attempts": st["attempts"], "errors": st["errors"], "steps": steps,
              "live_verify": {"ok": bool(checks) and all(c["ok"] for c in checks) if st["status"] != "failed" else False, "checks": checks},
              "journal": {"events": st["n_events"], "head": st["head"]},
              "note": "Квитанция собрана runner-ом из журнала и повторного чтения состояния; не со слов модели."}
        path = os.path.join(self.receipts_dir, "ACT-task-%s.json" % tid)
        rc["path"] = path
        if write:
            atomic_write(path, (json.dumps(rc, ensure_ascii=False, indent=1) + "\n").encode())
        return rc

    # --- канбан/календарь (формат selftools/task_board: queue.jsonl + flock .lock)
    def _sync(self, st):
        d = self.dispatch_dir
        if not d or not st.get("id"):
            return
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".lock"), "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            qp = os.path.join(d, "queue.jsonl")
            q = []
            if os.path.exists(qp):
                with open(qp, encoding="utf-8") as qf:
                    for l in qf:
                        if l.strip():
                            try:
                                q.append(json.loads(l))
                            except ValueError:
                                pass
            rec = {"id": "act-" + st["id"], "title": st["title"] or st["id"], "kind": "act", "status": st["status"],
                   "column": KANBAN.get(st["status"], "todo"), "key": st["key"], "attempts": st["attempts"],
                   "receipt": os.path.join(self.receipts_dir, "ACT-task-%s.json" % st["id"]),
                   "steps_done": sum(1 for s in st["steps"].values() if s["status"] == "done"), "steps_total": len(st["steps"]),
                   "ts": st.get("submitted")}
            for i, x in enumerate(q):
                if x.get("id") == rec["id"]:
                    q[i] = {**x, **rec}
                    break
            else:
                q.append(rec)
            atomic_write(qp, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in q).encode())
            cp = os.path.join(d, "act_calendar.json")
            cal = jload(cp) if os.path.exists(cp) else {"events": []}
            ev = {"id": "act-" + st["id"], "title": st["title"] or st["id"], "status": st["status"],
                  "start": datetime.fromtimestamp(st.get("started") or st.get("submitted") or time.time(), MSK).isoformat(),
                  "end": datetime.fromtimestamp(st.get("finished") or time.time(), MSK).isoformat() if st.get("finished") else None}
            cal["events"] = [e for e in cal["events"] if e["id"] != ev["id"]] + [ev]
            atomic_write(cp, (json.dumps(cal, ensure_ascii=False, indent=1) + "\n").encode())


# ---------------------------------------------------------------- приёмка N задач
def accept(acc_path, home, receipts_dir=None):
    """Для каждой задачи: submit x2 (дубля нет) -> [обрыв ->] resume -> проверка -> откат x2 -> проверка «как до»."""
    acc = jload(acc_path)
    ws = os.path.join(home, "ws")
    r = Runner(ws, home, dispatch_dir=os.path.join(home, "dispatch"), receipts_dir=receipts_dir)
    results = []
    for t in acc["tasks"]:
        card, exp = t["card"], t.get("expect", "done")
        for rel, content in (t.get("seed") or {}).items():
            atomic_write(os.path.join(ws, rel), content.encode())
        pre = {rel: _hash_or_none(os.path.join(ws, rel)) for rel in t.get("touches", [])}
        row = {"id": card["id"], "expect": exp, "checks": {}}
        s1, s2 = r.submit(card), r.submit(card)
        row["checks"]["submit_idempotent"] = (not s1["dup"]) and s2["dup"]
        cr = t.get("crash")
        if cr:
            def hook(step, point, cr=cr, fired=[False]):
                if not fired[0] and step == cr["step"] and point == cr["point"]:
                    fired[0] = True
                    raise Crash()
            try:
                r.run(card["id"], crash=hook)
                row["checks"]["crashed"] = False
            except Crash:
                row["checks"]["crashed"] = True
            row["status_after_crash"] = r.state(card["id"])["status"]
        res = r.run(card["id"])
        row["status"] = res["status"]
        row["checks"]["status_as_expected"] = res["status"] == exp
        if exp == "done":
            row["checks"]["receipt_verified"] = res["verified"]
            for kind in t.get("expect_lines", []):
                n = (_read(_safe(ws, kind["path"])) or b"").decode().split("\n").count(kind["line"])
                row["checks"]["no_duplicate_effect:" + kind["line"][:24]] = n == 1
            back = r.rollback(card["id"])
            back2 = r.rollback(card["id"])
            row["checks"]["rollback_ok"] = back["status"] == "rolled_back" and back["verified"] and back2["status"] == "rolled_back"
        else:
            row["checks"]["auto_rollback_verified"] = res.get("verified", False)
        post = {rel: _hash_or_none(os.path.join(ws, rel)) for rel in t.get("touches", [])}
        row["checks"]["restored_exactly"] = post == pre
        row["ok"] = all(row["checks"].values())
        results.append(row)
    out = {"id": "ACT-ACCEPT-%d" % len(results), "total": len(results), "passed": sum(1 for x in results if x["ok"]),
           "ok": all(x["ok"] for x in results), "results": results, "ts": time.time()}
    atomic_write(os.path.join(r.receipts_dir, out["id"] + ".json"), (json.dumps(out, ensure_ascii=False, indent=1) + "\n").encode())
    return out


def _hash_or_none(p):
    b = _read(p)
    return sha_b(b) if b is not None else None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="task_runner")
    ap.add_argument("--home", default=os.environ.get("NOX_ACT_HOME", "/root/nox/state/act"))
    ap.add_argument("--ws", default=None)
    ap.add_argument("--dispatch", default=os.environ.get("NOX_DISPATCH_DIR"))
    ap.add_argument("--receipts", default=os.environ.get("NOX_RECEIPTS", "/root/nox/receipts"))
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("submit", "run", "rollback", "status", "receipt", "list", "accept", "stale"):
        p = sp.add_parser(n)
        if n not in ("list", "stale"):
            p.add_argument("arg")
    sp.choices["stale"].add_argument("--minutes", type=int, default=60)
    ns = ap.parse_args(argv)
    r = Runner(ns.ws or os.path.join(ns.home, "ws"), ns.home, ns.dispatch, ns.receipts)
    if ns.cmd == "accept":
        out = accept(ns.arg, ns.home, ns.receipts)
    elif ns.cmd == "submit":
        out = r.submit(jload(ns.arg))
    elif ns.cmd == "run":
        out = r.run(ns.arg)
    elif ns.cmd == "rollback":
        out = r.rollback(ns.arg)
    elif ns.cmd == "stale":
        out = {"ok": True, "stale": r.stale(ns.minutes)}
    elif ns.cmd == "status":
        out = {k: v for k, v in r.state(ns.arg).items() if k != "card"}
    elif ns.cmd == "receipt":
        out = r.receipt(ns.arg, write=True)
    else:
        out = [{"id": s["id"], "status": s["status"], "column": KANBAN.get(s["status"])} for s in r.list_tasks()]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if (out.get("ok", True) if isinstance(out, dict) else True) else 1


if __name__ == "__main__":
    sys.exit(main())
