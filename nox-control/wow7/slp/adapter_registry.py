#!/usr/bin/env python3
"""SLP-05 adapter_registry: реестр LoRA-адаптеров «спинного мозга» NOX: кандидат -> принят/отклонён -> откат.
Хранит /root/nox/state/adapters/registry.json (атомарно, под flock). Принятие вызывает selftools lora_swap (симлинк + рестарт + health + авто-откат),
если заданы NOX_LORA_SERVICE и NOX_SELFTOOLS; иначе только переключает симлинк. Лимит дрейфа: не более одного принятия в сутки (--force обходит).
Команды: register | promote | reject | rollback | status | list | prune. Только stdlib.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import statefile
import argparse, fcntl, hashlib, json, os, subprocess, sys, time

ROOT = os.environ.get("NOX_ADAPTERS", "/root/nox/state/adapters")
DAY = 86400


def paths(root=None):
    r = root or ROOT
    return {"root": r, "reg": os.path.join(r, "registry.json"), "lock": os.path.join(r, ".lock"), "link": os.environ.get("NOX_LORA_LINK", os.path.join(r, "current.gguf"))}


class Locked:
    def __init__(self, p):
        os.makedirs(p["root"], exist_ok=True)
        self.f = open(p["lock"], "w")

    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def load(p):
    if not os.path.exists(p["reg"]):
        return {"version": 1, "entries": [], "current": None, "history": []}
    return json.load(open(p["reg"], encoding="utf-8"))


def save(p, d):
    statefile.save(p["reg"], d, indent=1)


def sha256(fp):
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def find(d, aid):
    for e in d["entries"]:
        if e["id"] == aid:
            return e
    raise KeyError("адаптер не найден: %s" % aid)


def register(p, gguf, base, peft_dir=None, metrics=None, parent=None, aid=None, note=""):
    if not os.path.isfile(gguf):
        raise FileNotFoundError(gguf)
    with Locked(p):
        d = load(p)
        sha = sha256(gguf)
        for e in d["entries"]:
            if e["sha256"] == sha:
                return e  # идемпотентно: тот же файл не регистрируем дважды
        aid = aid or time.strftime("lora-%Y%m%d-%H%M%S") + "-" + sha[:6]
        if any(e["id"] == aid for e in d["entries"]):
            raise ValueError("id занят: " + aid)
        e = {"id": aid, "gguf": os.path.abspath(gguf), "peft_dir": peft_dir, "base": base, "sha256": sha, "size": os.path.getsize(gguf),
             "created": int(time.time()), "status": "candidate", "parent": parent or d["current"], "metrics": metrics or {}, "note": note}
        d["entries"].append(e)
        save(p, d)
        return e


def _swap(p, path):
    """Переключить адаптер. Возвращает (ok, подробности)."""
    svc, st = os.environ.get("NOX_LORA_SERVICE"), os.environ.get("NOX_SELFTOOLS")
    if svc and st:
        args = {"action": "swap", "link": p["link"], "adapter": path, "service": svc, "dry_run": False}
        if os.environ.get("NOX_LORA_HEALTH"):
            args["health_url"] = os.environ["NOX_LORA_HEALTH"]
        r = subprocess.run([sys.executable, st, "lora_swap", "--args", json.dumps(args)], capture_output=True, text=True, timeout=600)
        try:
            out = json.loads(r.stdout)
        except ValueError:
            return False, {"error": "lora_swap вернул не JSON", "stderr": r.stderr[-200:]}
        return bool(out.get("ok")), out
    tmp = p["link"] + ".new%d" % os.getpid()
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(path, tmp)
    os.replace(tmp, p["link"])
    return True, {"mode": "symlink-only", "link": p["link"], "target": path}


def promote(p, aid, force=False, gate=None):
    """gate: dict с ключом pass (результат fidelity_test) — без pass=true принятие запрещено."""
    with Locked(p):
        d = load(p)
        e = find(d, aid)
        if not (gate and gate.get("pass") is True):
            raise PermissionError("gate не пройден или не передан: адаптер не принимается")
        if sha256(e["gguf"]) != e["sha256"]:
            raise ValueError("sha256 файла изменился: " + aid)
        today = [h for h in d["history"] if h["action"] == "promote" and time.time() - h["t"] < DAY]
        if today and not force:
            raise PermissionError("лимит дрейфа: уже принят адаптер за последние 24 ч (%s)" % today[-1]["id"])
        ok, info = _swap(p, e["gguf"])
        if not ok:
            return {"ok": False, "id": aid, "swap": info}
        prev = d["current"]
        if prev:
            find(d, prev)["status"] = "retired"
        e["status"], e["accepted"] = "accepted", int(time.time())
        d["current"] = aid
        d["history"].append({"t": int(time.time()), "action": "promote", "id": aid, "previous": prev})
        save(p, d)
        return {"ok": True, "id": aid, "previous": prev, "swap": info}


def reject(p, aid, reason):
    with Locked(p):
        d = load(p)
        e = find(d, aid)
        if e["status"] == "accepted":
            raise ValueError("принятый адаптер не отклоняют, используйте rollback")
        e["status"], e["reject_reason"] = "rejected", reason
        d["history"].append({"t": int(time.time()), "action": "reject", "id": aid, "reason": reason})
        save(p, d)
        return {"ok": True, "id": aid}


def rollback(p):
    """Вернуть последний предыдущий принятый (retired) адаптер; если его нет — отвязать симлинк (чистый базовый спинной мозг)."""
    with Locked(p):
        d = load(p)
        cur = d["current"]
        if not cur:
            return {"ok": False, "error": "нет текущего адаптера"}
        prev = next((h["previous"] for h in reversed(d["history"]) if h["action"] == "promote" and h["id"] == cur), None)
        if prev:
            ok, info = _swap(p, find(d, prev)["gguf"])
            if not ok:
                return {"ok": False, "swap": info}
            find(d, prev)["status"] = "accepted"
        else:
            if os.path.islink(p["link"]):
                os.remove(p["link"])
            info = {"mode": "unlinked", "note": "работает базовая модель без адаптера (нужен рестарт сервиса)"}
        find(d, cur)["status"] = "rolled_back"
        d["current"] = prev
        d["history"].append({"t": int(time.time()), "action": "rollback", "id": cur, "previous": prev})
        save(p, d)
        return {"ok": True, "rolled_back": cur, "now": prev, "swap": info}


def prune(p, keep=5):
    """Удалить файлы старых отклонённых/откатанных/отставных (кроме текущего и keep последних)."""
    with Locked(p):
        d = load(p)
        dead = [e for e in d["entries"] if e["status"] in ("rejected", "rolled_back", "retired") and e["id"] != d["current"] and not e.get("pruned")]
        dead.sort(key=lambda e: e["created"])
        freed = 0
        for e in dead[:max(0, len(dead) - keep)]:
            if os.path.isfile(e["gguf"]):
                freed += e["size"]
                os.remove(e["gguf"])
            e["pruned"] = True
        save(p, d)
        return {"ok": True, "freed_bytes": freed}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("register"); r.add_argument("gguf"); r.add_argument("--base", required=True); r.add_argument("--peft-dir")
    r.add_argument("--metrics", help="JSON"); r.add_argument("--id"); r.add_argument("--note", default="")
    pr = sp.add_parser("promote"); pr.add_argument("id"); pr.add_argument("--gate", required=True, help="report.json из fidelity_test.py"); pr.add_argument("--force", action="store_true")
    rj = sp.add_parser("reject"); rj.add_argument("id"); rj.add_argument("--reason", required=True)
    sp.add_parser("rollback"); sp.add_parser("status"); sp.add_parser("list")
    pn = sp.add_parser("prune"); pn.add_argument("--keep", type=int, default=5)
    a = ap.parse_args(argv)
    p = paths(a.root)
    try:
        if a.cmd == "register":
            out = register(p, a.gguf, a.base, a.peft_dir, json.loads(a.metrics) if a.metrics else None, aid=a.id, note=a.note)
        elif a.cmd == "promote":
            rep = json.load(open(a.gate, encoding="utf-8"))
            out = promote(p, a.id, a.force, rep.get("gate"))
        elif a.cmd == "reject":
            out = reject(p, a.id, a.reason)
        elif a.cmd == "rollback":
            out = rollback(p)
        elif a.cmd == "prune":
            out = prune(p, a.keep)
        else:
            d = load(p)
            out = {"current": d["current"], "link": p["link"], "target": os.readlink(p["link"]) if os.path.islink(p["link"]) else None} if a.cmd == "status" else \
                  [{k: e[k] for k in ("id", "status", "created", "base", "parent", "metrics")} for e in d["entries"]]
    except (KeyError, ValueError, FileNotFoundError, PermissionError) as e:
        print(json.dumps({"ok": False, "error": type(e).__name__, "detail": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if not isinstance(out, dict) or out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
