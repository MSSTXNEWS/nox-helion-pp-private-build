"""warm_weights: тёплые веса с ПК владельца -> RAM сервера (/dev/shm), и бэкапы сервер -> ПК.
Канал: обратный SSH-туннель с ПК (PCLINK_START.cmd) => http://127.0.0.1:18765 на сервере. Без туннеля инструмент честно отвечает blocked."""
import json
import os
import urllib.error
import urllib.request
import registry as R

BASE = os.environ.get("NOX_PC_LINK", "http://127.0.0.1:18765")
WARM = os.environ.get("NOX_WARM_DIR", "/dev/shm/nox_warm")
BACKUP_ROOTS = ("/root/nox/state", "/root/nox/lora", "/root/nox/memory", "/root/nox/knowledge", "/root/nox/datasets", "/root/nox/scripts")
NEED = "владелец: запустить PCLINK_START.cmd на ПК (окно открыто); если ключ новый — сообщить Claude для авторизации"


def _req(path, method="GET", headers=None, data=None, timeout=15):
    r = urllib.request.Request(BASE + path, method=method, headers=headers or {}, data=data)
    return urllib.request.urlopen(r, timeout=timeout)


def _clean(rel):
    rel = rel.strip("/")
    if not rel or ".." in rel.split("/") or "\\" in rel or any(c in rel for c in "\n\r\0"):
        raise R.Denied("bad path")
    return rel


@R.register("warm_weights", "write", {"properties": {
    "action": {"type": "string", "enum": ["status", "list", "pull", "evict", "backup_push"]},
    "path": {"type": "string"}, "max_gb": {"type": "number", "default": 40}},
    "required": ["action"]},
    "status/list (читать), pull <path>: докачать файл с ПК в /dev/shm/nox_warm (RAM), evict <имя>: выгрузить из RAM, "
    "backup_push <локальный файл из /root/nox/...>: отправить бэкап на ПК. dry_run по умолчанию для pull/backup_push.")
def warm_weights(a):
    act = a["action"]
    if act == "status":
        os.makedirs(WARM, exist_ok=True)
        st = os.statvfs(WARM)
        files = [{"name": n, "gb": round(os.path.getsize(os.path.join(WARM, n)) / 2**30, 2)} for n in sorted(os.listdir(WARM))]
        try:
            _req("/", timeout=5).read(1)
            link = True
        except Exception as e:  # noqa
            link = False
        return {"ok": True, "pc_link": link, "warm_dir": WARM, "free_gb": round(st.f_bavail * st.f_frsize / 2**30, 1), "warm": files,
                **({} if link else {"blocked": "ПК не подключён", "need": NEED})}
    try:
        if act == "list":
            rel = _clean(a["path"]) if a.get("path") else ""
            return {"ok": True, "entries": json.loads(_req("/" + rel).read())}
        if act == "evict":
            name = os.path.basename(_clean(a["path"]))
            p = os.path.join(WARM, name)
            if not os.path.isfile(p):
                return R.fail("not in RAM: " + name)
            if a["dry_run"]:
                return {"ok": True, "dry_run": True, "would_free_gb": round(os.path.getsize(p) / 2**30, 2)}
            os.remove(p)
            return {"ok": True, "evicted": name}
        if act == "pull":
            rel = _clean(a["path"])
            head = urllib.request.urlopen(urllib.request.Request(BASE + "/" + rel, method="HEAD"), timeout=15)
            size = int(head.headers["Content-Length"])
            os.makedirs(WARM, exist_ok=True)
            st = os.statvfs(WARM)
            free = st.f_bavail * st.f_frsize
            out = os.path.join(WARM, os.path.basename(rel))
            have = os.path.getsize(out) if os.path.exists(out) else 0
            plan = {"file": rel, "size_gb": round(size / 2**30, 2), "have_gb": round(have / 2**30, 2), "free_ram_gb": round(free / 2**30, 1)}
            if size > a["max_gb"] * 2**30:
                return R.fail("слишком большой файл", **plan)
            if size - have + 4 * 2**30 > free:
                return R.blocked("не хватает места в /dev/shm: " + json.dumps(plan), "выгрузить другое (evict) или меньшая модель")
            if a["dry_run"]:
                return {"ok": True, "dry_run": True, **plan}
            hdr = {"Range": "bytes=%d-" % have} if have else {}
            with _req("/" + rel, headers=hdr, timeout=60) as r, open(out, "ab" if have else "wb") as f:
                for b in iter(lambda: r.read(1 << 20), b""):
                    f.write(b)
            if os.path.getsize(out) != size:
                return R.fail("размер не совпал (можно повторить pull для докачки)", **plan)
            return {"ok": True, "warm": out, **plan}
        if act == "backup_push":
            src = R.safe_path(a["path"], must_exist=True, allow=list(BACKUP_ROOTS))
            if not os.path.isfile(src):
                return R.fail("нужен файл (сначала tar): " + src)
            name = os.path.basename(src)
            if a["dry_run"]:
                return {"ok": True, "dry_run": True, "file": src, "gb": round(os.path.getsize(src) / 2**30, 2)}
            with open(src, "rb") as f:
                req = urllib.request.Request(BASE + "/backups/" + name, method="PUT", data=f,
                                             headers={"Content-Length": str(os.path.getsize(src))})
                return {"ok": True, "pc": json.loads(urllib.request.urlopen(req, timeout=3600).read())}
    except urllib.error.HTTPError as e:
        return R.fail("PC HTTP %s" % e.code)
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        return R.blocked("ПК недоступен: %s" % e, NEED)
    return R.fail("unknown action")
