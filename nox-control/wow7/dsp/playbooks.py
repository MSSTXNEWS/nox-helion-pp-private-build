"""DSP плейбуки: диагностика -> действие -> честный результат. Вызываются диспетчером (dispatch по коду причины, run_global каждый такт).
Каждый плейбук с кулдауном и суточным лимитом (нет петель). Чистка — только по белому списку и не трогает protected.
Все функции принимают диспетчер d и возвращают {"ok": bool, "text": str, "actions": [...]}."""
import glob
import json
import os
import re
import shutil
import subprocess
import time

import nox_dispatcher as nd

SHARD_RX = re.compile(r"^GLM-5\.3-UD-Q4_K_XL-(\d{5})-of-00011\.gguf$")


def res(ok, text, *actions, **kw):
    r = {"ok": ok, "text": text, "actions": list(actions)}
    r.update(kw)
    return r


# ------------------------------------------------------------ GLM: шарды
def shard_name(i):
    return "GLM-5.3-UD-Q4_K_XL-%05d-of-00011.gguf" % i


def shard_live_path(d, i):
    g = d.reg.glm
    return os.path.join(g["shards_shm"] if i <= g.get("shards_in_shm", 9) else g["shards_disk"], shard_name(i))


def newest_receipt(d):
    files = sorted(glob.glob(os.path.join(d.home, "logs", "redo_sha_receipt-*.json")), key=os.path.getmtime)
    return (files[-1], nd.load_json(files[-1], {})) if files else (None, {})


def glm_shards_state(d):
    """Все 11 шардов на своих местах и размер совпадает с эталоном из последней квитанции (если она есть)."""
    g = d.reg.glm
    _, rc = newest_receipt(d)
    sizes = {n: v.get("size") for n, v in (rc.get("sources") or {}).items()}
    missing, bad = [], []
    for i in range(1, g.get("shards_total", 11) + 1):
        p = shard_live_path(d, i)
        if not os.path.isfile(p):
            missing.append(i)
        elif os.path.getsize(p) == 0 or (sizes.get(shard_name(i)) and os.path.getsize(p) != sizes[shard_name(i)]):
            bad.append(i)
    if not os.path.exists(g["model"]) and not missing:
        missing.append(1)
    if missing or bad:
        return False, "шарды GLM: нет %s, неверный размер %s (после остановки Vast /dev/shm мог очиститься)" % (missing or "-", bad or "-")
    return True, "все шарды на месте"


def parse_redo_launch(out):
    m = re.search(r"expected_receipt=(\S+)", out or "")
    return m.group(1) if m else None


def publish_from_receipt(d, rc):
    """Переложить проверенные (sha) файлы на боевые места атомарным rename. Без повторного хеша 435 ГиБ: сверяем dev/inode/mtime/size
    с квитанцией воркера (он проверил sha сразу перед записью квитанции). Отказ, если GLM работает или есть STOP."""
    if d.stop_active():
        return res(False, "STOP активен, публикация не делается")
    if nd.find_pids(d.reg.x(d.reg.services["glm"]["match"])):
        return res(False, "GLM-процесс жив, публикация шардов запрещена")
    if rc.get("shard_count") != d.reg.glm.get("shards_total", 11) or "ALL_11_SHA_VERIFIED" not in str(rc.get("state")):
        return res(False, "квитанция не подтверждает 11/11 sha")
    plan = []
    for name, src in sorted((rc.get("sources") or {}).items()):
        m = SHARD_RX.match(name)
        if not m:
            return res(False, "странное имя шарда в квитанции: %s" % name)
        live = shard_live_path(d, int(m.group(1)))
        p = src["path"]
        try:
            stt = os.stat(p, follow_symlinks=False)
        except OSError:
            return res(False, "файл из квитанции исчез: " + p)
        if os.path.islink(p) or (stt.st_dev, stt.st_ino, stt.st_mtime_ns, stt.st_size) != (src["device"], src["inode"], src["mtime_ns"], src["size"]):
            return res(False, "файл %s изменился после проверки sha: публикация отменена" % name)
        plan.append((name, p, live))
    acts = []
    for name, p, live in plan:
        if os.path.realpath(p) != os.path.realpath(live):
            os.makedirs(os.path.dirname(live), exist_ok=True)
            os.replace(p, live)
            acts.append("rename %s" % name)
        link = os.path.join(os.path.dirname(d.reg.glm["model"]), name)
        if not os.path.lexists(link) and os.path.realpath(link) != os.path.realpath(live):
            os.makedirs(os.path.dirname(link), exist_ok=True)
            os.symlink(live, link)
            acts.append("symlink %s" % name)
    return res(True, "опубликовано %d шардов (проверенных sha)" % len(plan), *acts)


def pb_glm_shards(d, name, reason):
    g = d.reg.glm
    ok, detail = glm_shards_state(d)
    st = d.ss(name)
    # 1) воркер уже качает
    worker = nd.find_pids(r"redo_worker\.py")
    if worker:
        parts = [os.path.getsize(p) for p in glob.glob(os.path.join(g["shards_shm"], ".nox_verified", "*", "*.part")) + glob.glob(os.path.join(g["shards_disk"], ".nox_verified", "*", "*.part"))]
        return res(True, "перекачка идёт (pid %s), докачано частей: %d, %.1f ГиБ" % (worker[0], len(parts), sum(parts) / 2 ** 30), "wait")
    # 2) готова квитанция после начала инцидента -> публикуем
    rp, rc = newest_receipt(d)
    if rp and os.path.getmtime(rp) >= st.get("redo_started", 0):
        pub = publish_from_receipt(d, rc)
        if pub["ok"]:
            st["backoff_until"] = 0
            st["fails"] = 0
            ok2, det2 = glm_shards_state(d)
            return res(ok2, pub["text"] + "; " + det2, *pub["actions"])
        if not ok:
            pass  # публикация не удалась и шардов нет -> ниже запустим перекачку заново
        else:
            return pub
    if ok and reason.get("code") == "model_missing" and st.get("fails", 0) < 3:
        return res(True, "шарды на месте, ошибка загрузки модели: повторим по backoff (перекачка при >=3 подряд)", "retry")
    # 3) запуск перекачки
    script = g.get("redo_script_local") if os.path.isfile(g.get("redo_script_local", "")) else g.get("redo_script")
    if not script or not os.path.isfile(script):
        return res(False, "нет скрипта перекачки %s (git pull репозитория)" % script)
    if d.dry:
        return res(True, "dry-run: запустил бы bash %s" % script, "dry")
    r = subprocess.run(["bash", script], capture_output=True, text=True, timeout=60)
    out = (r.stdout + r.stderr).strip()
    st["redo_started"] = d.now()
    if r.returncode == 75 and ("BUSY" in out or "WORKER_ACTIVE" in out):
        return res(True, "перекачка уже запущена другим процессом: " + out[-120:], "wait")
    return res(r.returncode in (0, 75), "перекачка с проверкой sha запущена: " + out[-200:], "redo_started", receipt=parse_redo_launch(out))


# ------------------------------------------------------------ шлюз 502
def pb_gateway_502(d, name, reason):
    fast = d.reg.services.get("fast")
    fobs = d.observe("fast") if fast else {"state": "UP"}
    if fobs["state"] != "UP":
        st = d.ss("fast")
        st["backoff_until"] = 0
        if fobs["state"] == "DOWN" and not d.dry:
            d.start("fast", "gateway_502: тир-основа лежит")
        return res(True, "причина 502: быстрый тир :8083 в состоянии %s, поднимаю его, шлюз не трогаю" % fobs["state"], "start fast")
    s = d.reg.services[name]
    if d.dry:
        return res(True, "dry-run: перезапустил бы шлюз", "dry")
    d.stop(name, grace=5)
    d.ss(name)["backoff_until"] = 0
    d.start(name, "playbook gateway_502")
    end = time.time() + s.get("start_timeout_s", 30)
    while time.time() < end:
        code, _ = nd.http("GET", "http://127.0.0.1:%d%s" % (s["port"], s["health"]["path"]), timeout=2)
        if code in s["health"]["ok"]:
            pr = s["probe"]
            c2, _ = nd.http(pr["method"], "http://127.0.0.1:%d%s" % (s["port"], pr["path"]), pr.get("body"), pr.get("timeout_s", 30))
            return res(c2 not in pr["bad"] and c2 is not None, "шлюз перезапущен, проба чата: %s (было %s)" % (c2, reason.get("probe_code")), "restart gateway")
        time.sleep(0.5)
    return res(False, "шлюз перезапущен, но health не поднялся за %d с" % s.get("start_timeout_s", 30), "restart gateway")


# ------------------------------------------------------------ быстрая модель не та
def pb_fast_model(d, name, reason):
    if d.dry:
        return res(True, "dry-run: перезапуск с %s" % reason.get("want"), "dry")
    d.stop(name)
    d.ss(name)["backoff_until"] = 0
    d.start(name, "playbook fast_model: %s -> %s" % (os.path.basename(reason.get("have", "")), os.path.basename(reason.get("want", ""))))
    return res(True, "быстрый тир перезапущен под модель реестра %s" % os.path.basename(reason.get("want", "")), "restart fast")


# ------------------------------------------------------------ порт занят
def port_owner(port):
    inodes = set()
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for line in open(f).read().splitlines()[1:]:
                p = line.split()
                if p[3] == "0A" and int(p[1].rsplit(":", 1)[1], 16) == port:
                    inodes.add(p[9])
        except OSError:
            pass
    for pid_dir in glob.glob("/proc/[0-9]*/fd"):
        try:
            for fd in os.listdir(pid_dir):
                try:
                    link = os.readlink(os.path.join(pid_dir, fd))
                except OSError:
                    continue
                if link.startswith("socket:[") and link[8:-1] in inodes:
                    return int(pid_dir.split("/")[2])
        except OSError:
            continue
    return None


def pb_port_busy(d, name, reason):
    s = d.reg.services[name]
    pid = port_owner(s["port"]) if s.get("port") else None
    if not pid:
        return res(True, "порт %s уже свободен" % s.get("port"), "none")
    cmd = " ".join(nd.cmdline_args(pid))
    own = re.search(d.reg.x(s["match"]), cmd) if s.get("match") else False
    if own:
        if not d.dry:
            nd.kill_pids([pid], 5)
            d.ss(name)["backoff_until"] = 0
        return res(True, "порт %s держал зависший экземпляр %s (pid %d) - убит" % (s["port"], name, pid), "kill %d" % pid)
    return res(False, "порт %s занят ЧУЖИМ процессом pid %d: %s - не трогаю, нужен человек" % (s["port"], pid, cmd[:120]))


# ------------------------------------------------------------ OOM при старте
def pb_oom_start(d, name, reason):
    acts = []
    info = ""
    if shutil.which("nvidia-smi"):
        info = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    shed = shed_background(d, "oom_start")
    return res(True, "%s при старте %s; выгружено фона: %s; GPU-процессы: %s. Флаги -ngl/-c не меняю сам (это A/B-тюнинг)" % (reason["code"], name, shed or "нечего", info.replace("\n", "; ") or "н/д"), *shed)


def shed_background(d, why):
    out = []
    for n in sorted(d.reg.services, key=lambda x: -d.reg.services[x].get("prio", 50)):
        s = d.reg.services[n]
        if s.get("group") == "bg":
            st = d.ss(n)
            if nd.find_pids(d.reg.x(s["match"])) and not st.get("suspended"):
                d.stop(n, grace=5)
            if not st.get("suspended"):
                st["suspended"] = why
                out.append(n)
    return out


# ------------------------------------------------------------ глобальные
def safe_path(d, path):
    """Можно ли трогать path: под белым списком и вне protected."""
    rp = os.path.realpath(path)
    prot = [os.path.realpath(p) for p in d.pol.get("protected", [])]
    if any(rp == p or rp.startswith(p + os.sep) for p in prot):
        return False
    roots = [os.path.realpath(p) for p in d.pol.get("safe_clean", [])]
    return any(rp.startswith(r + os.sep) for r in roots)


def rm_safe(d, path):
    if not safe_path(d, path):
        return 0
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            size = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(path) for f in fs if os.path.isfile(os.path.join(a, f)))
            if not d.dry:
                shutil.rmtree(path, ignore_errors=True)
            return size
        size = os.path.getsize(path)
        if not d.dry:
            os.remove(path)
        return size
    except OSError:
        return 0


def clean_safe(d):
    freed, acts = 0, []
    now = d.now()
    for root in d.pol.get("safe_clean", []):
        if not os.path.isdir(root):
            continue
        base = root.rstrip("/")
        if base == "/tmp":
            for a, _, fs in os.walk(root):
                for f in fs:
                    p = os.path.join(a, f)
                    try:
                        stt = os.lstat(p)
                    except OSError:
                        continue
                    if stt.st_size > 1 << 20 and now - stt.st_mtime > 86400 and os.path.isfile(p) and not os.path.islink(p):
                        freed += rm_safe(d, p)
        elif base.endswith("/dl/gh"):
            for g in glob.glob(base + "/*/.git"):
                freed += rm_safe(d, g)
        elif base.startswith("/var/cache/apt"):
            for g in glob.glob(base + "/archives/*.deb"):
                freed += rm_safe(d, g)
        else:
            for ch in glob.glob(base + "/*"):
                freed += rm_safe(d, ch)
        acts.append(root)
    mx = d.pol.get("log_max_mb", 200) * 2 ** 20
    for lg in glob.glob(os.path.join(d.home, "logs", "*")):
        if os.path.isfile(lg) and os.path.getsize(lg) > mx and not d.dry:
            keep = min(5 << 20, mx // 2)
            with open(lg, "r+b") as f:
                f.seek(-keep, 2)
                tail = f.read()
                f.seek(0)
                f.truncate(0)
                f.write(tail)
            freed += mx - keep
            acts.append("trim " + os.path.basename(lg))
    return freed, acts


def check_disk(d):
    return d.sys.disk_free_gb() < d.pol["disk_min_free_gb"]


def pb_disk_low(d):
    before = d.sys.disk_free_gb()
    freed, acts = clean_safe(d)
    after = d.sys.disk_free_gb()
    if after < d.pol["disk_min_free_gb"]:
        return res(False, "диск: %.1f ГБ свободно (<%s), безопасная чистка освободила %.2f ГБ, этого мало; крупное (модели, бэкапы) сам не удаляю - нужен человек" % (after, d.pol["disk_min_free_gb"], freed / 2 ** 30), *acts)
    return res(True, "диск: было %.1f -> стало %.1f ГБ свободно" % (before, after), *acts)


def check_oom(d):
    avail = d.sys.mem_available_gb()
    if avail < d.pol["mem_min_available_gb"] and not d.st.get("oom_active"):
        return "low"
    if d.st.get("oom_active") and avail >= d.pol["mem_resume_available_gb"]:
        return "recovered"
    return None


def pb_oom(d, kind):
    if kind == "low":
        d.st["oom_active"] = True
        shed = shed_background(d, "oom")
        return res(True, "мало памяти (%.0f ГБ < %s): фон выгружен %s; чат (fast/glm/gateway) не трогаю" % (d.sys.mem_available_gb(), d.pol["mem_min_available_gb"], shed or "(фона уже нет)"), *shed)
    d.st["oom_active"] = False
    back = []
    for n in d.reg.services:
        st = d.ss(n)
        if st.get("suspended") in ("oom", "oom_start"):
            st["suspended"] = None
            st["backoff_until"] = 0
            back.append(n)
    return res(True, "память восстановилась (%.0f ГБ): фон разрешён %s" % (d.sys.mem_available_gb(), back), *back)


def check_dup_exclusive(d):
    dups = {}
    tags = {}
    for n, s in d.reg.services.items():
        if s.get("exclusive"):
            tags.setdefault(s["exclusive"], []).append(n)
    for tag, names in tags.items():
        pids = sorted({p for n in names for p in nd.find_pids(d.reg.x(d.reg.services[n]["match"]))})
        if len(pids) > 1:
            dups[tag] = pids
    return dups or None


def pb_dup_exclusive(d, dups):
    acts = []
    for tag, pids in dups.items():
        keep = min(pids, key=nd.proc_start_ticks)
        extra = [p for p in pids if p != keep]
        if not d.dry:
            nd.kill_pids(extra, 10)
        acts.append("%s: оставлен pid %d, убраны %s" % (tag, keep, extra))
    return res(True, "найдено несколько главных моделей - " + "; ".join(acts), *acts)


GLOBALS = [
    ("disk_low", check_disk, pb_disk_low, 300, 48),
    ("oom", check_oom, pb_oom, 20, 500),
    ("dup_exclusive", check_dup_exclusive, pb_dup_exclusive, 60, 100),
]

SERVICE_PB = [
    ("gateway_502", lambda n, c: n == "gateway" and c.startswith("chat_probe_"), pb_gateway_502, 120, 20),
    ("glm_shards", lambda n, c: n == "glm" and c in ("shards_missing", "model_missing"), pb_glm_shards, 45, 400),
    ("fast_model", lambda n, c: c == "model_mismatch", pb_fast_model, 900, 3),
    ("port_busy", lambda n, c: c == "port_busy", pb_port_busy, 120, 10),
    ("oom_start", lambda n, c: c in ("oom_gpu", "oom_host", "killed"), pb_oom_start, 300, 10),
]


def _gate(d, key, cooldown, max_day):
    rec = d.st["pb"].setdefault(key, {"ts": 0, "day": []})
    now = d.now()
    rec["day"] = [t for t in rec["day"] if now - t < 86400]
    if now - rec["ts"] < cooldown or len(rec["day"]) >= max_day:
        return False
    if key.split(":")[0] in d.pol.get("playbooks_disabled", []):
        return False
    rec["ts"] = now
    rec["day"].append(now)
    return True


def dispatch(d, name, reason):
    out = []
    if d.stop_active():
        return out
    for pbn, match, fn, cd, mx in SERVICE_PB:
        if match(name, reason["code"]) and _gate(d, "%s:%s" % (pbn, name), cd, mx):
            try:
                r = fn(d, name, reason)
            except Exception as e:  # noqa: BLE001
                r = res(False, "плейбук упал: %s: %s" % (type(e).__name__, e))
            r["playbook"] = pbn
            d.ev("playbook", name, "%s: %s" % (pbn, r["text"]), ok=r["ok"], playbook=pbn)
            out.append(r)
    return out


def run_global(d):
    for pbn, check, fn, cd, mx in GLOBALS:
        arg = check(d)
        if arg and _gate(d, "%s:*" % pbn, cd if pbn != "oom" else 0, mx):
            try:
                r = fn(d, arg) if pbn in ("oom", "dup_exclusive") else fn(d)
            except Exception as e:  # noqa: BLE001
                r = res(False, "плейбук упал: %s: %s" % (type(e).__name__, e))
            d.ev("playbook", None, "%s: %s" % (pbn, r["text"]), ok=r["ok"], playbook=pbn)
