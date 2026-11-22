#!/usr/bin/env python3
"""DSP updater: тянуть новую версию диспетчера из main (raw.githubusercontent), проверить, применить атомарно, откатить при провале health.
Раскладка install_dir (/root/nox/dsp): releases/<ver>/, current -> releases/<ver>, previous -> прежний релиз, updates.json, local.json (локальные правки, не трогаются).
Проверки до применения: sha256 каждого файла из MANIFEST.json, только имена [A-Za-z0-9_.-], py_compile, bash -n, json, unittest релиза.
Применение: staging-каталог -> rename в releases -> атомарная подмена симлинка current -> restart (execv диспетчера).
Откат: (а) restart вернулся, а health не поднялся -> откат здесь; (б) диспетчер не стартовал -> watchdog.sh откатывает симлинк по pending из updates.json.
Доверие: канал TLS до raw.githubusercontent.com репозитория владельца; подписи нет (нет ключа) - риск описан в CARDS.md. Целостность файлов проверяется манифестом из того же коммита."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import hashlib
import json

import statefile
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

NAME_RX = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ALLOWED_EXT = (".py", ".sh", ".json", ".md", ".service", ".yml")
RELEASE_EXT = (".py", ".sh", ".json", ".service")  # документы в релиз не входят
REQUIRED = ("nox_dispatcher.py", "playbooks.py", "updater.py", "wake.py", "watchdog.sh", "services.json", "test_dsp.py", "fake_service.py")
MAX_FILE = 2 * 2 ** 20


class UpdateError(Exception):
    pass


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def version_of(files):
    return sha256_bytes("\n".join("%s:%s" % (k, files[k]) for k in sorted(files)).encode())[:12]


def make_manifest(src_dir, names=None):
    names = names or sorted(f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f)) and f.endswith(RELEASE_EXT) and f != "MANIFEST.json")
    files = {n: sha256_bytes(open(os.path.join(src_dir, n), "rb").read()) for n in names}
    return {"version": version_of(files), "files": files}


def default_fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "nox-dsp-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise UpdateError("файл больше %d байт: %s" % (MAX_FILE, url))
    return data


def atomic_symlink(target, link):
    tmp = "%s.new.%d" % (link, os.getpid())
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, link)


class Updater:
    def __init__(self, base_url, install_dir, clock=time.time, fetch=None, run_tests=True, health_timeout=60, keep=3):
        self.base = base_url.rstrip("/")
        self.dir = install_dir
        self.clock = clock
        self.fetch = fetch or default_fetch
        self.run_tests = run_tests
        self.health_timeout = health_timeout
        self.keep = keep
        self.state_path = os.path.join(install_dir, "updates.json")
        os.makedirs(os.path.join(install_dir, "releases"), exist_ok=True)

    # ---- состояние
    def state(self):
        try:
            return json.load(open(self.state_path))
        except (OSError, ValueError):
            return {"bad": [], "history": [], "pending": None}

    def save(self, st):
        statefile.save(self.state_path, st, indent=1)

    def current_version(self):
        try:
            return open(os.path.join(self.dir, "current", "VERSION")).read().strip()
        except OSError:
            return None

    def _link_target(self, name):
        p = os.path.join(self.dir, name)
        return os.path.basename(os.readlink(p)) if os.path.islink(p) else None

    # ---- скачивание и проверки
    def fetch_manifest(self):
        m = json.loads(self.fetch(self.base + "/MANIFEST.json").decode("utf-8"))
        files = m.get("files")
        if not isinstance(files, dict) or not files:
            raise UpdateError("манифест без files")
        if len(files) > 40:
            raise UpdateError("в манифесте слишком много файлов")
        for n, h in files.items():
            if not NAME_RX.match(n) or not n.endswith(ALLOWED_EXT) or n.startswith("."):
                raise UpdateError("недопустимое имя файла в манифесте: %r" % n)
            if not re.fullmatch(r"[0-9a-f]{64}", str(h)):
                raise UpdateError("плохой sha256 для %s" % n)
        miss = [r for r in REQUIRED if r not in files]
        if miss:
            raise UpdateError("в манифесте нет обязательных файлов: %s" % miss)
        if m.get("version") != version_of(files):
            raise UpdateError("version манифеста не сходится с хешами файлов")
        return m

    def stage(self, manifest):
        ver = manifest["version"]
        sd = os.path.join(self.dir, "releases", ".stage-" + ver)
        shutil.rmtree(sd, ignore_errors=True)
        os.makedirs(sd)
        for n, h in manifest["files"].items():
            data = self.fetch(self.base + "/" + n)
            if sha256_bytes(data) != h:
                raise UpdateError("sha256 не сошёлся для %s" % n)
            with open(os.path.join(sd, n), "wb") as f:
                f.write(data)
            if n.endswith(".sh"):
                os.chmod(os.path.join(sd, n), 0o755)
        with open(os.path.join(sd, "VERSION"), "w") as f:
            f.write(ver + "\n")
        return sd

    def verify(self, sd):
        for n in sorted(os.listdir(sd)):
            p = os.path.join(sd, n)
            if n.endswith(".py"):
                try:
                    compile(open(p, encoding="utf-8").read(), p, "exec")
                except (SyntaxError, ValueError) as e:
                    raise UpdateError("синтаксис %s: %s" % (n, str(e)[:200]))
            elif n.endswith(".sh"):
                r = subprocess.run(["bash", "-n", p], capture_output=True, text=True)
                if r.returncode:
                    raise UpdateError("bash -n %s: %s" % (n, r.stderr[:200]))
            elif n.endswith(".json"):
                try:
                    json.load(open(p))
                except ValueError as e:
                    raise UpdateError("json %s: %s" % (n, e))
        if self.run_tests:
            env = dict(os.environ, DSP_TEST_QUICK="1", PYTHONDONTWRITEBYTECODE="1")
            env.pop("DSP_HOME", None)
            r = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", sd, "-p", "test_dsp.py"], cwd=sd, env=env, capture_output=True, text=True, timeout=600)
            if r.returncode:
                raise UpdateError("тесты релиза красные: " + (r.stderr or r.stdout)[-300:])

    # ---- применение/откат
    def apply(self, sd, ver, restart=None, health=None):
        st = self.state()
        rel = os.path.join(self.dir, "releases", ver)
        if os.path.exists(rel):
            shutil.rmtree(rel)
        os.rename(sd, rel)
        prev = self._link_target("current")
        if prev:
            atomic_symlink(os.path.join("releases", prev), os.path.join(self.dir, "previous"))
        atomic_symlink(os.path.join("releases", ver), os.path.join(self.dir, "current"))
        st["pending"] = {"version": ver, "prev": prev, "since": self.clock(), "deadline": self.clock() + self.health_timeout + 120}
        self.save(st)
        if restart is None:
            return {"ok": True, "applied": ver, "prev": prev, "verified": None}
        restart()  # в бою это execv и сюда управление не вернётся; verify сделает новый диспетчер (commit_if_healthy) или watchdog (откат)
        if health is None:
            return {"ok": True, "applied": ver, "prev": prev, "verified": None}
        end = self.clock() + self.health_timeout
        while self.clock() < end:
            if health(ver):
                self.commit(ver)
                return {"ok": True, "applied": ver, "prev": prev, "verified": True}
            time.sleep(0.2)
        self.rollback("health не поднялся за %d с" % self.health_timeout, restart=restart)
        return {"ok": False, "rolled_back": True, "bad": ver, "back_to": prev, "error": "health не поднялся"}

    def commit(self, ver):
        st = self.state()
        if st.get("pending") and st["pending"]["version"] == ver:
            st["pending"] = None
            st["history"] = (st["history"] + [{"ts": self.clock(), "version": ver, "ok": True}])[-30:]
            self.save(st)
        rel = sorted((d for d in os.listdir(os.path.join(self.dir, "releases")) if not d.startswith(".")),
                     key=lambda d: os.path.getmtime(os.path.join(self.dir, "releases", d)), reverse=True)
        keep = {self._link_target("current"), self._link_target("previous")} | set(rel[:self.keep])
        for d in rel:
            if d not in keep:
                shutil.rmtree(os.path.join(self.dir, "releases", d), ignore_errors=True)

    def rollback(self, why, restart=None):
        st = self.state()
        bad = self._link_target("current")
        prev = self._link_target("previous") or (st.get("pending") or {}).get("prev")
        if not prev or not os.path.isdir(os.path.join(self.dir, "releases", prev)):
            raise UpdateError("нет предыдущего релиза для отката")
        atomic_symlink(os.path.join("releases", prev), os.path.join(self.dir, "current"))
        if bad and bad not in st["bad"]:
            st["bad"].append(bad)
        st["pending"] = None
        st["history"] = (st["history"] + [{"ts": self.clock(), "version": bad, "ok": False, "why": why, "back_to": prev}])[-30:]
        self.save(st)
        if restart:
            restart()
        return prev

    def check_and_apply(self, restart=None, health=None):
        st = self.state()
        if st.get("pending"):
            return {"ok": True, "changed": False, "note": "предыдущее обновление ещё не подтверждено"}
        try:
            m = self.fetch_manifest()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "changed": False, "error": "манифест: %s: %s" % (type(e).__name__, e)}
        ver = m["version"]
        if ver == self.current_version():
            return {"ok": True, "changed": False, "version": ver}
        if ver in st["bad"]:
            return {"ok": True, "changed": False, "note": "версия %s ранее откатана как плохая" % ver}
        sd = None
        try:
            sd = self.stage(m)
            self.verify(sd)
        except Exception as e:  # noqa: BLE001
            if sd:
                shutil.rmtree(sd, ignore_errors=True)
            st["bad"].append(ver)
            st["history"] = (st["history"] + [{"ts": self.clock(), "version": ver, "ok": False, "why": str(e)[:300]}])[-30:]
            self.save(st)
            return {"ok": False, "changed": False, "rejected": ver, "error": str(e)[:300]}
        r = self.apply(sd, ver, restart=restart, health=health)
        r["changed"] = r.get("ok", False)
        return r

    def install_initial(self, src_dir):
        """Первичная установка из локального каталога (install_dsp_s1.sh): файлы проверяются так же, как при обновлении."""
        m = make_manifest(src_dir)
        sd = os.path.join(self.dir, "releases", ".stage-" + m["version"])
        shutil.rmtree(sd, ignore_errors=True)
        os.makedirs(sd)
        for n in m["files"]:
            shutil.copy2(os.path.join(src_dir, n), os.path.join(sd, n))
        open(os.path.join(sd, "VERSION"), "w").write(m["version"] + "\n")
        self.verify(sd)
        self.apply(sd, m["version"])
        self.commit(m["version"])
        return m["version"]


def commit_if_healthy(install_dir, my_version, tick_n, min_ticks=3):
    """Вызывает новый диспетчер: после min_ticks успешных тактов подтверждает свою версию (снимает pending)."""
    u = Updater("http://invalid", install_dir)
    p = (u.state().get("pending") or {})
    if p and p.get("version") == my_version and tick_n >= min_ticks:
        u.commit(my_version)
        return True
    return False


def main(argv):
    cmd = argv[0] if argv else "status"
    home = os.environ.get("DSP_HOME", "/root/nox")
    inst = os.environ.get("DSP_INSTALL", os.path.join(home, "dsp"))
    base = os.environ.get("DSP_UPDATE_URL", "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/wow7/dsp")
    u = Updater(base, inst)
    if cmd == "manifest":
        d = argv[1]
        m = make_manifest(d)
        with open(os.path.join(d, "MANIFEST.json"), "w") as f:
            json.dump(m, f, indent=1)
        print(m["version"])
    elif cmd == "check":
        print(json.dumps(u.check_and_apply(restart=None), ensure_ascii=False))
    elif cmd == "rollback":
        print("откат к", u.rollback(" ".join(argv[1:]) or "ручной откат"))
    elif cmd == "install":
        print(u.install_initial(argv[1]))
    else:
        print(json.dumps({"current": u.current_version(), "state": u.state()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
