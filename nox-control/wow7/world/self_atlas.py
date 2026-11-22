#!/usr/bin/env python3
"""self_atlas: автокарта NOX - «знает каждый винтик». Stdlib only; ничего не меняет в системе (только читает).

Сканирует: процессы (/proc), слушающие порты с владельцем-процессом, службы (systemd/supervisor, если есть), модели и их
файлы (gguf/safetensors, шарды), GPU (nvidia-smi), RAM/CPU/диск (cgroup-aware), модули репо nox-control (AST: docstring,
классы, функции, импорты) и связи «кто кого вызывает» (импорты между модулями + обращения к портам сервисов).
Выход: JSON-атлас (/root/nox/state/self_atlas.json) и «устройство меня» (self_atlas.md). Раз в час: `loop` или cron.
answer(вопрос, атлас) отвечает на «как ты устроен?», «что на порту 8083?», «что делает модуль X?» ТОЛЬКО из атласа;
чего в атласе нет - говорит «не знаю». Расширяет selftools/self_map.py тем же форматом записи (file/doc/classes/functions/imports).
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import ast
import glob
import json

import statefile
import os
import re
import shutil
import subprocess
import sys
import time

MODEL_EXT = (".gguf", ".safetensors", ".bin", ".onnx")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def _read(path, limit=200000):
    try:
        with open(path, "rb") as f:
            return f.read(limit).decode("utf-8", "replace")
    except OSError:
        return ""


def _run(cmd, timeout=8):
    if not shutil.which(cmd[0]):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (subprocess.SubprocessError, OSError):
        return None


# ---------- процессы и порты ----------
def scan_processes(proc="/proc", min_rss_mb=0):
    out = []
    page = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
    for d in os.listdir(proc):
        if not d.isdigit():
            continue
        cmd = _read(os.path.join(proc, d, "cmdline"), 4000).replace("\x00", " ").strip()
        if not cmd:
            continue
        statm = _read(os.path.join(proc, d, "statm")).split()
        rss = int(statm[1]) * page / 1048576 if len(statm) > 1 and statm[1].isdigit() else 0
        if rss < min_rss_mb:
            continue
        out.append({"pid": int(d), "cmd": cmd[:300], "rss_mb": round(rss, 1),
                    "name": os.path.basename(cmd.split()[0]) if cmd.split() else "?"})
    return sorted(out, key=lambda x: -x["rss_mb"])


def scan_ports(proc="/proc"):
    """Слушающие TCP-порты -> [{port, pid, proc}] через inode сокета."""
    inodes = {}
    for fn in ("net/tcp", "net/tcp6"):
        for line in _read(os.path.join(proc, fn)).splitlines()[1:]:
            f = line.split()
            if len(f) > 9 and f[3] == "0A":        # LISTEN
                inodes[f[9]] = int(f[1].rsplit(":", 1)[1], 16)
    owners = {}
    for d in os.listdir(proc):
        if not d.isdigit():
            continue
        fdir = os.path.join(proc, d, "fd")
        try:
            for fd in os.listdir(fdir):
                try:
                    t = os.readlink(os.path.join(fdir, fd))
                except OSError:
                    continue
                m = re.match(r"socket:\[(\d+)\]", t)
                if m and m.group(1) in inodes:
                    owners[m.group(1)] = int(d)
        except OSError:
            continue
    res = []
    for ino, port in inodes.items():
        pid = owners.get(ino)
        cmd = _read(os.path.join(proc, str(pid), "cmdline"), 600).replace("\x00", " ").strip() if pid else ""
        res.append({"port": port, "pid": pid, "proc": cmd[:200] or "(владелец не виден)"})
    return sorted({r["port"]: r for r in res}.values(), key=lambda r: r["port"])


def scan_services():
    svc = []
    o = _run(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--no-pager", "--plain"])
    for line in (o or "").splitlines():
        f = line.split(None, 4)
        if len(f) >= 4:
            svc.append({"manager": "systemd", "name": f[0], "state": f[3], "desc": f[4] if len(f) > 4 else ""})
    o = _run(["supervisorctl", "status"])
    for line in (o or "").splitlines():
        f = line.split()
        if len(f) >= 2:
            svc.append({"manager": "supervisor", "name": f[0], "state": f[1], "desc": " ".join(f[2:])[:80]})
    return svc


# ---------- модели ----------
_SHARD = re.compile(r"^(.*?)-(\d{5})-of-(\d{5})(\.\w+)$")


def scan_models(dirs, max_files=400):
    """Файлы моделей; шарды llama.cpp (-00001-of-00011) сворачиваются в одну модель с суммарным размером."""
    groups = {}
    n = 0
    for base in dirs:
        for d, ds, fs in os.walk(base):
            ds[:] = [x for x in ds if x not in SKIP_DIRS]
            for f in fs:
                if not f.lower().endswith(MODEL_EXT):
                    continue
                fp = os.path.join(d, f)
                try:
                    sz = os.path.getsize(fp)
                except OSError:
                    continue
                m = _SHARD.match(f)
                key = os.path.join(d, m.group(1) + m.group(4)) if m else fp
                g = groups.setdefault(key, {"path": key, "files": 0, "size_gb": 0.0, "shards_expected": int(m.group(3)) if m else 1})
                g["files"] += 1
                g["size_gb"] = round(g["size_gb"] + sz / 2 ** 30, 3)
                n += 1
                if n >= max_files:
                    break
    for g in groups.values():
        g["complete"] = g["files"] >= g["shards_expected"]
    return sorted(groups.values(), key=lambda g: -g["size_gb"])


# ---------- железо ----------
def scan_hardware(meminfo="/proc/meminfo", disk_path="/"):
    mem = {}
    for line in _read(meminfo).splitlines():
        k, _, v = line.partition(":")
        if v.split():
            mem[k] = int(v.split()[0]) / 1048576
    cg = None
    for p in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        v = _read(p).strip()
        if v.isdigit() and int(v) < 2 ** 50:
            cg = int(v) / 2 ** 30
            break
    cpu_q = None
    q = _read("/sys/fs/cgroup/cpu.max").split()
    if len(q) == 2 and q[0].isdigit():
        cpu_q = round(int(q[0]) / int(q[1]), 1)
    gpus = []
    o = _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"])
    for line in (o or "").splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) >= 5:
            gpus.append({"name": f[0], "vram_total_mb": f[1], "vram_used_mb": f[2], "util_pct": f[3], "temp_c": f[4]})
    try:
        du = shutil.disk_usage(disk_path)
        disk = {"total_gb": round(du.total / 2 ** 30, 1), "free_gb": round(du.free / 2 ** 30, 1)}
    except OSError:
        disk = {}
    return {"ram_total_gb": round(mem.get("MemTotal", 0), 1), "ram_avail_gb": round(mem.get("MemAvailable", 0), 1),
            "cgroup_mem_limit_gb": round(cg, 1) if cg else None, "cpu_count": os.cpu_count(), "cpu_quota": cpu_q,
            "gpus": gpus, "disk": disk, "load": os.getloadavg() if hasattr(os, "getloadavg") else None}


# ---------- репо: модули и связи ----------
def scan_repo(root, rel_to=None, max_files=3000):
    rel_to = rel_to or root
    mods = []
    for d, ds, fs in os.walk(root):
        ds[:] = sorted(x for x in ds if x not in SKIP_DIRS)
        for f in sorted(fs):
            if not f.endswith(".py"):
                continue
            fp = os.path.join(d, f)
            try:
                with open(fp, encoding="utf-8") as fh:
                    src = fh.read()
                tree = ast.parse(src)
            except (SyntaxError, UnicodeDecodeError, OSError) as e:
                mods.append({"file": os.path.relpath(fp, rel_to), "error": str(e)[:100]})
                continue
            doc = (ast.get_docstring(tree) or "").strip().splitlines()
            imps = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    imps.update(x.name.split(".")[0] for x in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module:
                    imps.add(n.module.split(".")[0])
            strs = sorted({n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                           and re.fullmatch(r"[a-z][a-z0-9_]{4,40}", n.value)})[:200]
            ports = sorted({int(p) for p in re.findall(r"(?:127\.0\.0\.1|localhost|0\.0\.0\.0):(\d{4,5})", src)})
            mods.append({"file": os.path.relpath(fp, rel_to), "doc": doc[0][:200] if doc else "",
                         "classes": [n.name for n in tree.body if isinstance(n, ast.ClassDef)][:30],
                         "functions": [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))][:40],
                         "imports": sorted(imps), "names": strs, "ports": ports, "lines": src.count("\n") + 1})
            if len(mods) >= max_files:
                return mods
    return mods


def build_graph(mods, ports=None):
    """Рёбра: модуль -> модуль (импорт по имени файла) и модуль -> порт сервиса (обращение к localhost:порт)."""
    by_name = {}
    for m in mods:
        if "file" in m and m["file"].endswith(".py"):
            by_name.setdefault(os.path.basename(m["file"])[:-3], []).append(m["file"])
    edges = []
    for m in mods:
        for imp in m.get("imports", []):
            for tgt in by_name.get(imp, []):
                if tgt != m["file"]:
                    edges.append({"from": m["file"], "to": tgt, "kind": "import"})
        for nm in m.get("names", []):       # загрузка по имени строкой (importlib в registry)
            for tgt in by_name.get(nm, []):
                if tgt != m["file"] and nm not in m.get("imports", []):
                    edges.append({"from": m["file"], "to": tgt, "kind": "loads_by_name"})
        for p in m.get("ports", []):
            edges.append({"from": m["file"], "to": "port:%d" % p, "kind": "calls_port"})
    return edges


def callers_of(graph, target):
    return sorted({e["from"] for e in graph if e["to"] == target or e["to"].endswith("/" + target) or e["to"] == "port:%s" % target})


# ---------- сбор ----------
def build_atlas(repo_root=None, model_dirs=(), proc="/proc", now=time.time, min_rss_mb=50, disk_path="/"):
    ports = scan_ports(proc)
    procs = scan_processes(proc, min_rss_mb)
    mods = scan_repo(repo_root) if repo_root and os.path.isdir(repo_root) else []
    a = {"ts": now(), "host": os.uname().nodename if hasattr(os, "uname") else "?", "hardware": scan_hardware(disk_path=disk_path),
         "processes": procs[:40], "ports": ports, "services": scan_services(),
         "models": scan_models([d for d in model_dirs if os.path.isdir(d)]), "repo": mods,
         "graph": build_graph(mods, ports)}
    for p in a["ports"]:                     # кто слушает порт + кто к нему обращается
        p["callers"] = callers_of(a["graph"], str(p["port"]))
    return a


def describe(a):
    """Человекочитаемое «устройство меня» (markdown)."""
    hw = a["hardware"]
    L = ["# Устройство NOX (атлас от %s, хост %s)" % (time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(a["ts"])), a["host"]), "",
         "## Тело", "- RAM: %s ГБ всего, %s ГБ свободно%s; CPU: %s ядер%s; диск свободно %s ГБ" % (
             hw["ram_total_gb"], hw["ram_avail_gb"], (" (лимит cgroup %s ГБ)" % hw["cgroup_mem_limit_gb"]) if hw["cgroup_mem_limit_gb"] else "",
             hw["cpu_count"], (", квота %s" % hw["cpu_quota"]) if hw["cpu_quota"] else "", hw["disk"].get("free_gb", "?"))]
    for g in hw["gpus"] or []:
        L.append("- GPU: %s, VRAM %s/%s МБ, загрузка %s%%, %s°C" % (g["name"], g["vram_used_mb"], g["vram_total_mb"], g["util_pct"], g["temp_c"]))
    if not hw["gpus"]:
        L.append("- GPU: не видно (nvidia-smi недоступен)")
    L += ["", "## Что слушает порты"]
    for p in a["ports"]:
        L.append("- :%d - %s%s" % (p["port"], p["proc"][:110], ("; вызывают: " + ", ".join(p["callers"][:5])) if p.get("callers") else ""))
    L += ["", "## Модели (файлы)"]
    for m in a["models"][:15]:
        L.append("- %s: %s ГБ, файлов %d%s" % (m["path"], m["size_gb"], m["files"], "" if m["complete"] else " (НЕПОЛНАЯ: ждали %d)" % m["shards_expected"]))
    if not a["models"]:
        L.append("- файлов моделей в заданных каталогах нет")
    L += ["", "## Службы"]
    for s in a["services"][:30]:
        L.append("- [%s] %s: %s" % (s["manager"], s["name"], s["state"]))
    if not a["services"]:
        L.append("- systemd/supervisor недоступны или пусты")
    L += ["", "## Главные процессы (по памяти)"]
    for p in a["processes"][:8]:
        L.append("- pid %d %s: %s МБ - %s" % (p["pid"], p["name"], p["rss_mb"], p["cmd"][:80]))
    L += ["", "## Модули репо (%d)" % len(a["repo"])]
    for m in a["repo"][:60]:
        if "error" not in m:
            L.append("- %s: %s" % (m["file"], m["doc"] or "(без описания)"))
    L += ["", "Связей между модулями: %d." % len(a["graph"])]
    return "\n".join(L)


def save(a, state_dir):
    for name, data in (("self_atlas.json", json.dumps(a, ensure_ascii=False)), ("self_atlas.md", describe(a))):
        statefile.write_bytes(os.path.join(state_dir, name), data)


def load(state_dir):
    with open(os.path.join(state_dir, "self_atlas.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------- ответы из атласа ----------
def answer(q, a, max_age_s=7200, now=time.time):
    """Ответ на вопрос о себе ТОЛЬКО из атласа. Устаревший атлас помечается; нет данных - «не знаю»."""
    ql = q.lower()
    age = now() - a["ts"]
    tail = "" if age < max_age_s else " (атлас устарел на %d ч - данные могли измениться)" % (age // 3600)
    m = re.search(r"порт\w*\s*:?\s*(\d{1,5})|:(\d{4,5})", ql)
    if m:
        port = int(m.group(1) or m.group(2))
        for p in a["ports"]:
            if p["port"] == port:
                return "На порту %d слушает: %s%s.%s" % (port, p["proc"][:150], ("; к нему обращаются " + ", ".join(p["callers"][:5])) if p.get("callers") else "", tail)
        return "Порт %d в моём атласе не слушается.%s" % (port, tail)
    m = re.search(r"([\w\-/]+\.py)", ql)
    if m:
        name = m.group(1)
        for r in a["repo"]:
            if r.get("file", "").endswith(name):
                who = callers_of(a["graph"], r["file"])
                return "%s: %s Функций: %d, импортирует: %s. Его используют: %s.%s" % (
                    r["file"], (r["doc"].rstrip(".") + ".") if r["doc"] else "описания нет.", len(r["functions"]), ", ".join(r["imports"][:8]) or "ничего",
                    ", ".join(who[:6]) or "никто в репо", tail)
        return "Модуля %s в атласе нет (сканировано %d модулей).%s" % (name, len(a["repo"]), tail)
    if re.search(r"(модел|gguf|вес)", ql):
        if not a["models"]:
            return "В атласе нет файлов моделей." + tail
        return "Модели: " + "; ".join("%s - %s ГБ%s" % (os.path.basename(m["path"]), m["size_gb"], "" if m["complete"] else " (неполная)") for m in a["models"][:6]) + "." + tail
    if re.search(r"(gpu|видеокарт|vram|памят|ram|железо|диск)", ql):
        h = a["hardware"]
        g = "; ".join("%s %s/%s МБ" % (x["name"], x["vram_used_mb"], x["vram_total_mb"]) for x in h["gpus"]) or "GPU не видно"
        return "RAM %s ГБ (свободно %s), %s, диск свободно %s ГБ.%s" % (h["ram_total_gb"], h["ram_avail_gb"], g, h["disk"].get("free_gb", "?"), tail)
    if re.search(r"(устроен|архитектур|из чего|как ты работаешь|внутри)", ql):
        return describe(a)[:3500] + tail
    return "Этого в моём атласе нет; могу описать устройство целиком, порты, модели, железо или конкретный модуль."


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "loop", "ask"])
    ap.add_argument("question", nargs="*")
    ap.add_argument("--repo", default=os.environ.get("NOX_REPO", "/root/nox/src/nox-control"))
    ap.add_argument("--models", default=os.environ.get("NOX_MODEL_DIRS", "/root/nox/models:/root/models"))
    ap.add_argument("--state", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    ap.add_argument("--every", type=int, default=3600)
    a = ap.parse_args(argv)
    dirs = [d for d in a.models.split(":") if d]
    if a.cmd == "ask":
        print(answer(" ".join(a.question), load(a.state)))
        return 0
    while True:
        atlas = build_atlas(a.repo, dirs)
        save(atlas, a.state)
        print("atlas: %d портов, %d модулей, %d моделей" % (len(atlas["ports"]), len(atlas["repo"]), len(atlas["models"])), flush=True)
        if a.cmd == "scan":
            return 0
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
