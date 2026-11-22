"""Тесты DSP: настоящие подпроцессы (fake_service.py = python http-сервер), настоящий HTTP-сервер для updater, настоящий bash для watchdog.
Запуск: python3 -m unittest test_dsp -v   (DSP_TEST_QUICK=1 пропускает самые долгие)"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nox_dispatcher as nd  # noqa: E402
import playbooks  # noqa: E402
import wake  # noqa: E402
import updater  # noqa: E402

FAKE = os.path.join(HERE, "fake_service.py")
MSK = timezone(timedelta(hours=3))
QUICK = os.environ.get("DSP_TEST_QUICK") == "1"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def msk_ts(h, m=0):
    return datetime(2026, 11, 22, h, m, tzinfo=MSK).timestamp()


class Clock:
    def __init__(self, t=None):
        self.t = t if t is not None else time.time()

    def __call__(self):
        return self.t

    def adv(self, s):
        self.t += s


class FakeSys:
    def __init__(self, home):
        self.home, self.disk, self.mem = home, 100.0, 500.0

    def disk_free_gb(self, path=None):
        return self.disk() if callable(self.disk) else self.disk

    def mem_available_gb(self):
        return self.mem


BASE_POLICY = {"tick_s": 1, "quiet_hours_msk": [23, 8], "disk_min_free_gb": 5, "mem_min_available_gb": 24, "mem_resume_available_gb": 48,
               "backoff_s": [10, 30, 90], "backoff_s_heavy": [10, 30], "stable_reset_s": 600, "max_restarts_day": 12, "auto_update": False,
               "update_every_s": 21600, "update_base_url": "http://invalid", "forbidden_flags": ["--no-mmap", "--mlock", "-ctk", "-ctv", "--cache-type-k", "--cache-type-v"],
               "safe_clean": ["@HOME@/dl/npm", "@HOME@/dl/gh"], "protected": ["@HOME@/state", "@HOME@/memory", "@HOME@/glm53", "@HOME@/dl/hf", "@HOME@/receipts"], "log_max_mb": 1}


def fake(name, port, *extra, **kw):
    s = {"name": name, "group": kw.pop("group", "chat"), "port": port,
         "argv": [sys.executable, FAKE, "--port", str(port)] + list(extra),
         "match": "fake_service\\.py --port %d( |$)" % port, "health": {"path": "/health", "ok": [200], "loading": [503]},
         "load_grace_s": 60, "log": name + ".log", "start_timeout_s": 5}
    s.update(kw)
    return s


def make_reg(home, services, policy=None, glm=None):
    raw = {"home": home, "control": home + "/repo/nox-control", "policy": dict(BASE_POLICY, **(policy or {})),
           "glm": glm or {}, "env": {}, "services": services}
    return nd.Registry(raw, home=home)


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="dsp_t_")
        for d in ("logs", "state", "run", "memory"):
            os.makedirs(os.path.join(self.home, d))
        self.clock = Clock()
        self.stopf = os.path.join(self.home, "STOPFILE")
        os.environ["DSP_STOP_FILES"] = self.stopf
        os.environ["DSP_BOOT_MARKER"] = os.path.join(self.home, "bootmarker")
        open(os.environ["DSP_BOOT_MARKER"], "w").write("x")  # по умолчанию «не холодный старт»
        self.ds = []

    def tearDown(self):
        for d in self.ds:
            for n in d.reg.services:
                try:
                    d.stop(n, grace=2)
                except Exception:
                    pass
            for p in d.children.values():
                try:
                    p.kill()
                    p.wait(timeout=2)
                except Exception:
                    pass
        os.environ.pop("DSP_STOP_FILES", None)
        os.environ.pop("DSP_BOOT_MARKER", None)
        shutil.rmtree(self.home, ignore_errors=True)

    def disp(self, services, policy=None, glm=None, **kw):
        reg = make_reg(self.home, services, policy, glm)
        d = nd.Dispatcher(reg, clock=self.clock, sysinfo=kw.pop("sysinfo", FakeSys(self.home)), settle_s=0.6, **kw)
        self.ds.append(d)
        return d

    def until(self, d, cond, timeout=12, adv=0):
        end = time.time() + timeout
        while time.time() < end:
            d.tick()
            if cond():
                return True
            self.clock.adv(adv)
            time.sleep(0.3)
        return False

    def ev(self, d, kind, svc=None):
        return [e for e in d.st["events"] if e["kind"] == kind and (svc is None or e["svc"] == svc)]


# ---------------------------------------------------------------- реестр
class TestRegistry(unittest.TestCase):
    def test_real_registry_valid(self):
        r = nd.Registry.load(os.path.join(HERE, "services.json"), local_path="/nonexistent", home="/tmp/dsp_reg_home")
        order = r.order()
        self.assertLess(order.index("fast"), order.index("glm"))
        self.assertLess(order.index("glm"), order.index("gateway"))
        self.assertEqual(order[-1], "con_inner")
        ports = {s["port"] for s in r.services.values() if s.get("port")}
        self.assertTrue({8081, 8082, 8083, 8091, 8093, 8094, 8095} <= ports)
        self.assertEqual([n for n, s in r.services.items() if s.get("exclusive") == "glm"], ["glm"])
        argv, src, notes = r.glm_argv()
        self.assertEqual(src, "builtin")
        for bad in ("--no-mmap", "--mlock", "-ctk", "-ctv"):
            self.assertNotIn(bad, argv)
        self.assertIn("exps=CPU", argv)
        self.assertEqual(argv[argv.index("--port") + 1], "8081")

    def test_forbidden_flags_stripped_from_glm_args(self):
        home = tempfile.mkdtemp()
        try:
            os.makedirs(home + "/gpu_tier")
            open(home + "/gpu_tier/glm.args", "w").write("-c 4096 -ngl 30 --no-mmap --mlock -ctk q8_0 -ctv q8_0 --cache-type-k q4_0 -t 24")
            r = nd.Registry.load(os.path.join(HERE, "services.json"), local_path="/nonexistent", home=home)
            argv, src, notes = r.glm_argv()
            self.assertEqual(src, "glm.args")
            for bad in ("--no-mmap", "--mlock", "-ctk", "-ctv", "--cache-type-k", "q8_0", "q4_0"):
                self.assertNotIn(bad, argv)
            self.assertEqual(argv[argv.index("-c") + 1], "16384")
            self.assertTrue(any("-ctk" in n for n in notes))
        finally:
            shutil.rmtree(home)

    def test_winner_json_has_priority(self):
        home = tempfile.mkdtemp()
        try:
            os.makedirs(home + "/logs/spd_ab")
            json.dump({"args": ["-c", "32768", "-ngl", "30", "-t", "20"]}, open(home + "/logs/spd_ab/winner.json", "w"))
            r = nd.Registry.load(os.path.join(HERE, "services.json"), local_path="/nonexistent", home=home)
            argv, src, _ = r.glm_argv()
            self.assertEqual(src, "winner")
            self.assertEqual(argv[argv.index("-ngl") + 1], "30")
        finally:
            shutil.rmtree(home)

    def test_static_forbidden_flag_rejected(self):
        with self.assertRaises(nd.RegistryError):
            make_reg("/tmp/x", [fake("a", 1, "--no-mmap") | {}]) if False else make_reg("/tmp/x", [dict(fake("a", 1), argv=["llama-server", "--mlock"])])

    def test_two_main_models_rejected(self):
        with self.assertRaises(nd.RegistryError):
            make_reg("/tmp/x", [fake("g1", 1, exclusive="glm"), fake("g2", 2, exclusive="glm")])

    def test_cycle_and_dup_port_rejected(self):
        with self.assertRaises(nd.RegistryError):
            make_reg("/tmp/x", [fake("a", 1, after=["b"]), fake("b", 2, after=["a"])])
        with self.assertRaises(nd.RegistryError):
            make_reg("/tmp/x", [fake("a", 5), fake("b", 5)])

    def test_local_override(self):
        raw = json.load(open(os.path.join(HERE, "services.json")))
        r = nd.Registry(raw, home="/tmp/x", local={"policy": {"auto_update": False}, "services": {"fast": {"disabled": True}}, "glm": {"slot_dir": "/tmp/slots"}})
        self.assertFalse(r.policy["auto_update"])
        self.assertNotIn("fast", r.services)
        self.assertEqual(r.glm["slot_dir"], "/tmp/slots")

    def test_classify_reasons(self):
        self.assertEqual(nd.classify("bind: Address already in use")[0], "port_busy")
        self.assertEqual(nd.classify("CUDA error: out of memory")[0], "oom_gpu")
        self.assertEqual(nd.classify("", -9)[0], "killed")
        self.assertEqual(nd.classify("llama_model_load: error loading model: No such file")[0], "model_missing")


# ---------------------------------------------------------------- супервизор
class TestSupervise(Base):
    def test_start_health_and_adopt(self):
        p = free_port()
        d = self.disp([fake("a", p)])
        self.assertTrue(self.until(d, lambda: d.ss("a")["state"] == "UP"))
        pid = d.ss("a")["pid"]
        d2 = nd.Dispatcher(d.reg, clock=self.clock, sysinfo=FakeSys(self.home), settle_s=0.5)  # «рестарт диспетчера»: сервис усыновляется
        self.ds.append(d2)
        n0 = len(self.ev(d2, "start"))
        d2.tick()
        self.assertEqual(d2.ss("a")["state"], "UP")
        self.assertEqual(d2.ss("a")["pid"], pid)
        self.assertEqual(len(self.ev(d2, "start")), n0)

    def test_crash_reason_and_backoff(self):
        p = free_port()
        d = self.disp([fake("a", p, "--crash-after", "0.2", "--exit-code", "7", "--log-line", "CUDA error: out of memory")])
        d.tick()
        time.sleep(1.2)
        d.tick()  # заметили падение
        fails = self.ev(d, "fail", "a")
        self.assertTrue(fails)
        self.assertEqual(fails[-1]["code"], "oom_gpu")
        self.assertEqual(d.ss("a")["fails"], 1)
        n_start = len(self.ev(d, "start", "a"))
        d.tick()
        self.assertEqual(len(self.ev(d, "start", "a")), n_start)  # backoff держит
        self.assertEqual(d.ss("a")["last_reason"]["retry_in_s"], 10)
        self.clock.adv(11)
        d.tick()
        self.assertEqual(len(self.ev(d, "start", "a")), n_start + 1)
        time.sleep(1.2)
        d.tick()
        self.assertEqual(d.ss("a")["fails"], 2)
        self.assertEqual(d.ss("a")["last_reason"]["retry_in_s"], 30)

    def test_stable_resets_fails(self):
        p = free_port()
        d = self.disp([fake("a", p)])
        d.ss("a")["fails"] = 3
        self.assertTrue(self.until(d, lambda: d.ss("a")["state"] == "UP"))
        self.clock.adv(601)
        d.tick()
        self.assertEqual(d.ss("a")["fails"], 0)

    def test_requires_dependency(self):
        pa, pb = free_port(), free_port()
        d = self.disp([fake("a", pa, "--crash-after", "0.1"), fake("b", pb, requires=["a"])])
        d.ss("a")["backoff_until"] = self.clock() + 1000
        d.tick()
        self.assertEqual(d.ss("b")["last_reason"]["code"], "dep_down")
        self.assertEqual(len(self.ev(d, "start", "b")), 0)

    def test_loading_not_restarted_then_hung_killed(self):
        p = free_port()
        d = self.disp([fake("a", p, "--load-s", "1000", load_grace_s=5)])
        d.tick()
        time.sleep(0.5)
        d.tick()
        self.assertEqual(d.last_status["a"]["state"], "LOADING")
        self.assertEqual(len(self.ev(d, "start", "a")), 1)
        self.clock.adv(10)
        d.tick()
        self.assertTrue(self.ev(d, "hung", "a"))
        self.assertEqual(d.ss("a")["last_reason"]["code"], "hung_loading")
        time.sleep(0.5)
        self.assertEqual(nd.find_pids(d.reg.x(d.reg.services["a"]["match"])), [])

    def test_stop_file_freezes_everything(self):
        p = free_port()
        d = self.disp([fake("a", p)])
        open(self.stopf, "w").write("1")
        d.tick()
        d.tick()
        self.assertEqual(len(self.ev(d, "start", "a")), 0)
        hb = json.load(open(d.paths["hb"]))
        self.assertTrue(hb["frozen"])
        os.remove(self.stopf)
        self.assertTrue(self.until(d, lambda: d.ss("a")["state"] == "UP"))
        self.assertTrue(self.ev(d, "stop_cleared"))

    def test_quiet_hours(self):
        p = free_port()
        d = self.disp([fake("a", p, respect_quiet=True)])
        self.clock.t = msk_ts(2)
        d.tick()
        self.assertEqual(len(self.ev(d, "start", "a")), 0)
        self.assertEqual(d.ss("a")["last_reason"]["code"], "quiet_hours")
        self.clock.t = msk_ts(10)
        self.assertTrue(self.until(d, lambda: d.ss("a")["state"] == "UP"))
        self.assertTrue(d.in_quiet(msk_ts(23, 30)) and d.in_quiet(msk_ts(7, 59)) and not d.in_quiet(msk_ts(8)))

    def test_chat_priority_for_background(self):
        pf, pg, pb = free_port(), free_port(), free_port()
        d = self.disp([fake("fast", pf), fake("glm", pg, "--load-s", "2", heavy=True, exclusive="glm", after=["fast"]), fake("bgjob", pb, group="bg", after=["glm"])])
        d.ss("glm")["backoff_until"] = self.clock() + 1000  # glm не поднимается
        d.tick()
        time.sleep(1)
        d.tick()
        self.assertEqual(len(self.ev(d, "start", "bgjob")), 0)
        self.assertEqual(d.ss("bgjob")["last_reason"]["code"], "chat_priority")
        d.ss("glm")["backoff_until"] = 0
        self.assertTrue(self.until(d, lambda: d.ss("bgjob")["state"] == "UP", timeout=20))

    def test_manual_start_stop_cli_functions(self):
        p = free_port()
        d = self.disp([fake("a", p)])
        d.start("a", "manual")
        self.assertTrue(self.until(d, lambda: d.ss("a")["state"] == "UP"))
        d.stop("a")
        time.sleep(0.5)
        self.assertEqual(d.observe("a")["state"], "DOWN")


# ---------------------------------------------------------------- плейбуки
class TestPlaybooks(Base):
    def test_gateway_502_restarts_gateway(self):
        pf, pg = free_port(), free_port()
        code_file = os.path.join(self.home, "gw_code")
        probe = {"method": "POST", "path": "/v1/chat/completions", "body": {"x": 1}, "timeout_s": 5, "bad": [502, 503, 504], "every_s": 0}
        d = self.disp([fake("fast", pf), fake("gateway", pg, "--chat-code-file", code_file, requires=["fast"], probe=probe)])
        self.assertTrue(self.until(d, lambda: d.ss("gateway")["state"] == "UP"))
        pid0 = d.ss("gateway")["pid"]
        open(code_file, "w").write("502")
        d.tick()
        d.tick()
        pbs = [e for e in self.ev(d, "playbook", "gateway") if e["playbook"] == "gateway_502"]
        self.assertTrue(pbs, d.st["events"][-5:])
        d.tick()
        self.assertNotEqual(d.ss("gateway").get("pid"), pid0)
        self.assertIn("проба чата", pbs[-1]["text"])

    def test_gateway_502_when_fast_down_starts_fast_not_gateway(self):
        pf, pg = free_port(), free_port()
        code_file = os.path.join(self.home, "gw_code")
        probe = {"method": "POST", "path": "/v1/chat/completions", "body": {}, "timeout_s": 5, "bad": [502], "every_s": 0}
        d = self.disp([fake("fast", pf), fake("gateway", pg, "--chat-code-file", code_file, probe=probe)])
        self.assertTrue(self.until(d, lambda: d.ss("gateway")["state"] == "UP" and d.ss("fast")["state"] == "UP"))
        gw_pid = d.ss("gateway")["pid"]
        d.stop("fast")
        d.ss("fast")["backoff_until"] = self.clock() + 1000
        open(code_file, "w").write("502")
        d.tick()
        d.tick()
        r = [e for e in self.ev(d, "playbook", "gateway") if "быстрый тир" in e["text"]]
        self.assertTrue(r)
        self.assertEqual(nd.find_pids(d.reg.x(d.reg.services["gateway"]["match"]))[0], gw_pid)

    def test_fast_model_mismatch_restarts_with_registry_model(self):
        p = free_port()
        a, b = os.path.join(self.home, "a.gguf"), os.path.join(self.home, "b.gguf")
        open(b, "w").write("x")
        svc = fake("fast", p, model_candidates=[a, b])
        svc["argv"] += ["-m", "@MODEL@"]
        d = self.disp([svc])
        self.assertTrue(self.until(d, lambda: d.ss("fast")["state"] == "UP"))
        self.assertEqual(nd.cmdline_args(d.ss("fast")["pid"])[-1], b)
        open(a, "w").write("x")  # появилась нужная по реестру модель
        d.tick()
        self.assertTrue([e for e in self.ev(d, "playbook", "fast") if e["playbook"] == "fast_model"])
        self.assertTrue(self.until(d, lambda: d.ss("fast")["state"] == "UP" and nd.cmdline_args(d.ss("fast")["pid"])[-1] == a))
        n = len(self.ev(d, "playbook", "fast"))
        d.tick()
        self.assertEqual(len(self.ev(d, "playbook", "fast")), n)  # дальше не дёргаем

    def test_fast_model_missing_gives_honest_reason(self):
        p = free_port()
        svc = fake("fast", p, model_candidates=[os.path.join(self.home, "none.gguf")])
        svc["argv"] += ["-m", "@MODEL@"]
        d = self.disp([svc])
        d.tick()
        self.assertEqual(d.ss("fast")["last_reason"]["code"], "model_missing")

    def test_disk_low_cleans_only_safe_paths(self):
        h = self.home
        os.makedirs(h + "/dl/npm/pkg")
        open(h + "/dl/npm/pkg/big.bin", "wb").write(b"0" * 1000)
        os.makedirs(h + "/dl/gh/repo/.git")
        open(h + "/dl/gh/repo/.git/obj", "wb").write(b"0" * 500)
        open(h + "/dl/gh/repo/src.py", "w").write("keep")
        os.makedirs(h + "/dl/hf")
        open(h + "/dl/hf/model.gguf", "w").write("model")
        open(h + "/state/keep.json", "w").write("{}")
        open(h + "/memory/s03.db", "w").write("db")
        biglog = h + "/logs/big.log"
        open(biglog, "wb").write(b"L" * (3 * 2 ** 20))
        sysi = FakeSys(h)
        sysi.disk = lambda: 2.0 if os.path.exists(h + "/dl/npm/pkg") else 50.0
        d = self.disp([], sysinfo=sysi)
        d.tick()
        self.assertFalse(os.path.exists(h + "/dl/npm/pkg"))
        self.assertFalse(os.path.exists(h + "/dl/gh/repo/.git"))
        self.assertTrue(os.path.exists(h + "/dl/gh/repo/src.py"))
        for keep in ("/dl/hf/model.gguf", "/state/keep.json", "/memory/s03.db"):
            self.assertTrue(os.path.exists(h + keep), keep)
        self.assertLessEqual(os.path.getsize(biglog), 2 ** 20)
        r = [e for e in self.ev(d, "playbook") if e["playbook"] == "disk_low"]
        self.assertTrue(r and r[-1]["ok"])

    def test_disk_low_unresolved_is_honest(self):
        sysi = FakeSys(self.home)
        sysi.disk = 1.0
        d = self.disp([], sysinfo=sysi)
        d.tick()
        r = [e for e in self.ev(d, "playbook") if e["playbook"] == "disk_low"][-1]
        self.assertFalse(r["ok"])
        self.assertIn("нужен человек", r["text"])

    def test_safe_path_guard(self):
        d = self.disp([])
        for bad in ("/etc/passwd", self.home + "/state/x", self.home + "/glm53/a.gguf", self.home + "/dl/hf/m", "/", "/dev/shm/nox_glm/x"):
            self.assertFalse(playbooks.safe_path(d, bad), bad)
        self.assertTrue(playbooks.safe_path(d, self.home + "/dl/npm/x"))
        self.assertEqual(playbooks.rm_safe(d, "/etc/hostname"), 0)

    def test_oom_sheds_background_keeps_chat(self):
        pf, pb = free_port(), free_port()
        sysi = FakeSys(self.home)
        d = self.disp([fake("fast", pf), fake("bgjob", pb, group="bg", after=["fast"])], sysinfo=sysi)
        self.assertTrue(self.until(d, lambda: d.ss("bgjob")["state"] == "UP" and d.ss("fast")["state"] == "UP"))
        sysi.mem = 10.0
        d.tick()
        time.sleep(0.5)
        d.tick()
        self.assertEqual(d.ss("bgjob")["suspended"], "oom")
        self.assertEqual(d.observe("bgjob")["state"], "DOWN")
        self.assertEqual(d.observe("fast")["state"], "UP")
        n = len(self.ev(d, "start", "bgjob"))
        d.tick()
        self.assertEqual(len(self.ev(d, "start", "bgjob")), n)
        sysi.mem = 100.0
        self.assertTrue(self.until(d, lambda: d.observe("bgjob")["state"] == "UP"))
        self.assertFalse(d.st["oom_active"])

    def test_duplicate_main_model_killed(self):
        p1, p2 = free_port(), free_port()
        d = self.disp([fake("glm", p1, exclusive="glm", heavy=True)])
        d.reg.services["glm"]["match"] = "fake_service\\.py --port (%d|%d)( |$)" % (p1, p2)
        self.assertTrue(self.until(d, lambda: d.ss("glm")["state"] == "UP"))
        extra = subprocess.Popen([sys.executable, FAKE, "--port", str(p2)], start_new_session=True)
        time.sleep(0.7)
        d.tick()
        time.sleep(0.5)
        extra.poll()
        self.assertIsNotNone(extra.poll())
        self.assertEqual(len(nd.find_pids(d.reg.services["glm"]["match"])), 1)
        self.assertTrue([e for e in self.ev(d, "playbook") if e["playbook"] == "dup_exclusive"])

    def test_port_busy_foreign_owner_not_killed(self):
        p = free_port()
        holder = subprocess.Popen([sys.executable, FAKE, "--port", str(p), "--model", "holder", "--load-s", "1000"], start_new_session=True)
        try:
            time.sleep(0.7)
            d = self.disp([fake("a", p, match="svc_a_marker_never")])
            d.tick()
            time.sleep(0.5)
            self.assertEqual(d.ss("a")["last_reason"]["code"], "port_busy")
            r = [e for e in self.ev(d, "playbook", "a") if e["playbook"] == "port_busy"]
            self.assertTrue(r and not r[-1]["ok"] and "ЧУЖИМ" in r[-1]["text"])
            self.assertIsNone(holder.poll())
        finally:
            holder.kill()
            holder.wait()

    def _glm_setup(self, redo_ok=True):
        h = self.home
        glm = {"model": h + "/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf", "shards_shm": h + "/shm", "shards_disk": h + "/disk", "shards_total": 11, "shards_in_shm": 9,
               "redo_script": h + "/redo.sh", "redo_script_local": h + "/none.sh", "slot_dir": h + "/slots"}
        open(h + "/redo.sh", "w").write('#!/bin/bash\necho called >> %s/redo_calls\necho "PENDING_GGUF_SHA worker_pid=1 expected_receipt=%s/logs/redo_sha_receipt-T.json"\n' % (h, h))
        p = free_port()
        svc = fake("glm", p, heavy=True, exclusive="glm", preconditions=["glm_shards"])
        return self.disp([svc], glm=glm), glm

    def _make_receipt(self, h, tamper=False):
        sources = {}
        for i in range(1, 12):
            name = playbooks.shard_name(i)
            sd = h + ("/shm" if i <= 9 else "/disk") + "/.nox_verified/M"
            os.makedirs(sd, exist_ok=True)
            path = sd + "/" + name
            open(path, "wb").write(b"S" * (100 + i))
            st = os.stat(path)
            sources[name] = {"path": path, "sha256": "0" * 64, "size": st.st_size, "device": st.st_dev, "inode": st.st_ino, "mtime_ns": st.st_mtime_ns}
        rc = {"state": "ALL_11_SHA_VERIFIED_SOURCE_MANIFEST_HOLD_OWNER_CAS", "manifest_sha256": "M", "shard_count": 11, "sources": sources}
        rp = h + "/logs/redo_sha_receipt-T.json"
        json.dump(rc, open(rp, "w"))
        os.utime(rp, (self.clock() + 5, self.clock() + 5))
        if tamper:
            open(sources[playbooks.shard_name(3)]["path"], "ab").write(b"EVIL")
        return rc

    def test_glm_shards_missing_launches_redo_then_publishes_and_starts(self):
        d, glm = self._glm_setup()
        h = self.home
        d.tick()
        self.assertEqual(d.ss("glm")["last_reason"]["code"], "shards_missing")
        self.assertTrue(os.path.exists(h + "/redo_calls"))
        self.assertEqual(len(self.ev(d, "start", "glm")), 0)
        self.assertIn("перекачка", [e for e in self.ev(d, "playbook", "glm") if e["playbook"] == "glm_shards"][-1]["text"])
        self._make_receipt(h)
        self.clock.adv(60)
        d.ss("glm")["backoff_until"] = 0
        d.tick()  # precondition снова падает -> плейбук публикует
        for i in range(1, 12):
            self.assertTrue(os.path.isfile(playbooks.shard_live_path(d, i)), i)
        self.assertTrue(os.path.islink(h + "/glm53/" + playbooks.shard_name(2)))
        self.assertTrue(self.until(d, lambda: d.ss("glm")["state"] == "UP"))
        calls = open(h + "/redo_calls").read().count("called")
        self.assertEqual(calls, 1)

    def test_glm_publish_refused_when_file_changed_after_sha(self):
        d, glm = self._glm_setup()
        h = self.home
        d.tick()
        rc = self._make_receipt(h, tamper=True)
        r = playbooks.publish_from_receipt(d, rc)
        self.assertFalse(r["ok"])
        self.assertIn("изменился после проверки sha", r["text"])
        self.assertFalse(os.path.exists(playbooks.shard_live_path(d, 3)))

    def test_glm_publish_refused_under_stop_or_running_glm(self):
        d, glm = self._glm_setup()
        rc = self._make_receipt(self.home)
        open(self.stopf, "w").write("1")
        self.assertFalse(playbooks.publish_from_receipt(d, rc)["ok"])
        os.remove(self.stopf)
        os.makedirs(self.home + "/shm", exist_ok=True)
        pport = free_port()
        pr = subprocess.Popen([sys.executable, FAKE, "--port", str(pport)], start_new_session=True)
        try:
            d.reg.services["glm"]["match"] = "fake_service\\.py --port %d( |$)" % pport
            time.sleep(0.5)
            self.assertIn("GLM-процесс жив", playbooks.publish_from_receipt(d, rc)["text"])
        finally:
            pr.kill()
            pr.wait()

    def test_glm_shards_present_but_load_fails_waits_then_verifies(self):
        d, glm = self._glm_setup()
        for i in range(1, 12):
            p = playbooks.shard_live_path(d, i)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b"x")
        os.makedirs(self.home + "/glm53", exist_ok=True)
        open(glm["model"], "w").write("x")
        ok, _ = playbooks.glm_shards_state(d)
        self.assertTrue(ok)
        r = playbooks.pb_glm_shards(d, "glm", {"code": "model_missing"})
        self.assertIn("повторим по backoff", r["text"])
        self.assertFalse(os.path.exists(self.home + "/redo_calls"))
        d.ss("glm")["fails"] = 3
        r = playbooks.pb_glm_shards(d, "glm", {"code": "model_missing"})
        self.assertTrue(os.path.exists(self.home + "/redo_calls"))


# ---------------------------------------------------------------- пробуждение
FAKE_BUS = '''import json, os, time
class EventBus:
    def __init__(self, path, **kw):
        self.path = path; os.makedirs(os.path.dirname(path), exist_ok=True)
    def publish(self, type_, data=None, source=None):
        e = {"seq": 1, "ts": time.time(), "type": type_, "source": source, "data": data or {}}
        open(self.path, "a").write(json.dumps(e, ensure_ascii=False) + "\\n")
        return e
'''


class TestWake(Base):
    def _setup(self):
        h = self.home
        os.makedirs(h + "/repo/nox-control/qs6")
        open(h + "/repo/nox-control/qs6/__init__.py", "w").write("")
        open(h + "/repo/nox-control/qs6/events_bus.py", "w").write(FAKE_BUS)
        os.makedirs(h + "/src/con")
        con = os.path.join(HERE, "..", "CON", "nox_self_model_live.py")
        if not os.path.exists(con):
            self.skipTest("нет CON/nox_self_model_live.py")
        shutil.copy(con, h + "/src/con/")
        open(h + "/state/soul_prompt_ru.txt", "w").write("Ты NOX. Душа.")
        os.environ["NOX_EVENTS"] = h + "/memory/events.jsonl"
        os.environ["NOX_SELF_LIVE"] = h + "/state/self_live.json"
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("NOX_EVENTS", "NOX_SELF_LIVE")])
        pf, pg, pw = free_port(), free_port(), free_port()
        self.calls = h + "/glm_calls.log"
        return self.disp([fake("fast", pf), fake("glm", pg, "--calls-log", self.calls, heavy=True), fake("gateway", pw, requires=["fast"])])

    def test_cold_start_wakes_nox_and_warms_kv(self):
        d = self._setup()
        os.remove(os.environ["DSP_BOOT_MARKER"])
        self.clock.t = msk_ts(12)
        self.assertTrue(self.until(d, lambda: d.st["wake"].get("done_ts"), timeout=20))
        self.assertTrue(self.ev(d, "wake_pending"))
        live = json.load(open(self.home + "/state/self_live.json"))
        self.assertEqual(live["boots"], 1)
        self.assertEqual(live["milestones"][0]["kind"], "birth")
        lines = [json.loads(x) for x in open(self.home + "/memory/events.jsonl")]
        self.assertTrue(any(x["type"] == "nox.wake" for x in lines))
        body = json.loads(open(self.calls).read().splitlines()[0].split(" ", 2)[2])
        self.assertIs(body["cache_prompt"], True)
        self.assertEqual(body["messages"][0]["content"], "Ты NOX. Душа.")
        n = len(open(self.home + "/memory/events.jsonl").read().splitlines())
        d.tick()
        self.assertEqual(len(open(self.home + "/memory/events.jsonl").read().splitlines()), n)  # второй раз не будит

    def test_kv_warm_deferred_while_owner_chatting(self):
        d = self._setup()
        os.remove(os.environ["DSP_BOOT_MARKER"])
        self.clock.t = msk_ts(12)
        with open(self.home + "/state/self_live.json", "w") as f:
            json.dump({"last_owner_ts": self.clock()}, f)
        self.until(d, lambda: d.st["wake"].get("event"), timeout=15)
        for _ in range(3):
            d.tick()
        self.assertFalse(os.path.exists(self.calls) and "cache_prompt" in open(self.calls).read())
        self.assertTrue(d.st["wake"]["pending"])
        self.clock.adv(300)
        self.assertTrue(self.until(d, lambda: not d.st["wake"]["pending"], timeout=10))
        self.assertIn("cache_prompt", open(self.calls).read())

    def test_kv_warm_uses_spd_script_when_present(self):
        d = self._setup()
        os.makedirs(self.home + "/scripts")
        open(self.home + "/scripts/soul_kv_warm.sh", "w").write('#!/bin/bash\necho "$@" > %s/warm_args\n' % self.home)
        r = wake.warm_kv(d)
        self.assertTrue(r["ok"])
        self.assertIn("auto", open(self.home + "/warm_args").read())

    def test_glm_restart_triggers_rewarm(self):
        d = self._setup()
        self.clock.t = msk_ts(12)
        self.assertTrue(self.until(d, lambda: d.ss("glm")["state"] == "UP" and not d.st["wake"].get("pending", False) and d.st.get("glm_pid"), timeout=15))
        old = d.st["glm_pid"]
        d.stop("glm")
        d.ss("glm")["backoff_until"] = 0
        self.assertTrue(self.until(d, lambda: d.st.get("glm_pid") not in (None, old) and d.st["wake"].get("reason", "").startswith("GLM"), timeout=15))

    def test_morning_report_once_per_day_after_08(self):
        d = self._setup()
        self.clock.t = msk_ts(3)
        d.tick()
        self.assertFalse(list(__import__("glob").glob(self.home + "/state/dsp_morning_*.md")))
        self.clock.t = msk_ts(9)
        d.tick()
        files = list(__import__("glob").glob(self.home + "/state/dsp_morning_*.md"))
        self.assertEqual(len(files), 1)
        txt = open(files[0], encoding="utf-8").read()
        self.assertIn("Утренний отчёт", txt)
        n = len(self.ev(d, "morning_report"))
        d.tick()
        self.assertEqual(len(self.ev(d, "morning_report")), n)

    def test_morning_report_lists_incidents(self):
        d = self._setup()
        d.ev("fail", "gateway", "port_busy: порт занят")
        d.ev("playbook", "gateway", "gateway_502: ok", ok=True)
        txt = wake.morning_report(d, force=True)
        self.assertIn("port_busy", txt)
        self.assertIn("gateway_502", txt)


# ---------------------------------------------------------------- updater
def release(files_extra=None, tests_ok=True, bad_py=False, tamper=None):
    d = tempfile.mkdtemp(prefix="dsp_rel_")
    base = {"nox_dispatcher.py": "print('disp')\n", "playbooks.py": "X = 1\n", "updater.py": "Y = 1\n", "wake.py": "Z = 1\n",
            "watchdog.sh": "#!/bin/bash\nexit 0\n", "services.json": "{}\n", "fake_service.py": "pass\n",
            "test_dsp.py": "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertTrue(%s)\n" % ("True" if tests_ok else "False")}
    base.update(files_extra or {})
    if bad_py:
        base["wake.py"] = "def broken(:\n"
    for n, c in base.items():
        open(os.path.join(d, n), "w").write(c)
    m = updater.make_manifest(d)
    if tamper:
        open(os.path.join(d, tamper), "a").write("# tampered\n")
    return d, m


class Server:
    def __init__(self, directory):
        h = partial(SimpleHTTPRequestHandler, directory=directory)
        h.log_message = lambda *a: None

        class Q(SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Q, directory=directory))
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


class TestUpdater(unittest.TestCase):
    def setUp(self):
        self.inst = tempfile.mkdtemp(prefix="dsp_inst_")
        self.cleanup = [self.inst]
        self.srv = None
        self.restarts = 0
        # v1 установлен
        d1, m1 = release()
        self.v1 = updater.Updater("http://invalid", self.inst).install_initial(d1)
        self.cleanup.append(d1)

    def tearDown(self):
        if self.srv:
            self.srv.close()
        for d in self.cleanup:
            shutil.rmtree(d, ignore_errors=True)

    def serve(self, **kw):
        d, m = release(**kw)
        self.cleanup.append(d)
        self.srv = Server(d)
        json.dump(m, open(os.path.join(d, "MANIFEST.json"), "w"))
        return d, m

    def upd(self, **kw):
        return updater.Updater(self.srv.url, self.inst, health_timeout=2, **kw)

    def restart(self):
        self.restarts += 1

    def test_initial_install(self):
        self.assertEqual(updater.Updater("x", self.inst).current_version(), self.v1)
        self.assertTrue(os.path.islink(self.inst + "/current"))

    def test_good_update_applied_atomically_and_verified(self):
        d, m = self.serve(files_extra={"playbooks.py": "X = 2\n"})
        r = self.upd().check_and_apply(restart=self.restart, health=lambda v: True)
        self.assertTrue(r["ok"] and r["verified"], r)
        self.assertEqual(updater.Updater("x", self.inst).current_version(), m["version"])
        self.assertEqual(open(self.inst + "/current/playbooks.py").read(), "X = 2\n")
        self.assertEqual(os.path.basename(os.readlink(self.inst + "/previous")), self.v1)
        self.assertIsNone(updater.Updater("x", self.inst).state()["pending"])
        self.assertEqual(self.restarts, 1)
        r2 = self.upd().check_and_apply(restart=self.restart)
        self.assertFalse(r2["changed"])

    def test_syntax_error_rejected_and_not_retried(self):
        d, m = self.serve(bad_py=True)
        r = self.upd().check_and_apply(restart=self.restart)
        self.assertFalse(r["ok"])
        self.assertIn("синтаксис wake.py", r["error"])
        self.assertEqual(updater.Updater("x", self.inst).current_version(), self.v1)
        self.assertEqual(self.restarts, 0)
        self.assertIn("ранее откатана", self.upd().check_and_apply()["note"])

    def test_red_tests_rejected(self):
        d, m = self.serve(tests_ok=False)
        r = self.upd().check_and_apply(restart=self.restart)
        self.assertFalse(r["ok"])
        self.assertIn("тесты релиза красные", r["error"])
        self.assertEqual(updater.Updater("x", self.inst).current_version(), self.v1)

    def test_sha_mismatch_rejected(self):
        d, m = self.serve(tamper="services.json", files_extra={"playbooks.py": "X = 9\n"})
        r = self.upd().check_and_apply(restart=self.restart)
        self.assertFalse(r["ok"])
        self.assertIn("sha256 не сошёлся", r["error"])

    def test_path_traversal_and_missing_required_rejected(self):
        d, m = self.serve()
        m["files"]["../evil.py"] = "0" * 64
        m["version"] = updater.version_of(m["files"])
        json.dump(m, open(d + "/MANIFEST.json", "w"))
        self.assertIn("недопустимое имя", self.upd().check_and_apply()["error"])
        m2 = {"files": {"nox_dispatcher.py": "0" * 64}, "version": ""}
        m2["version"] = updater.version_of(m2["files"])
        json.dump(m2, open(d + "/MANIFEST.json", "w"))
        self.assertIn("обязательных", self.upd().check_and_apply()["error"])

    def test_forged_version_rejected(self):
        d, m = self.serve()
        m["version"] = "deadbeef0000"
        json.dump(m, open(d + "/MANIFEST.json", "w"))
        self.assertIn("version манифеста", self.upd().check_and_apply()["error"])

    def test_health_failure_rolls_back(self):
        d, m = self.serve(files_extra={"playbooks.py": "X = 3\n"})
        r = self.upd().check_and_apply(restart=self.restart, health=lambda v: False)
        self.assertFalse(r["ok"])
        self.assertTrue(r["rolled_back"])
        u = updater.Updater("x", self.inst)
        self.assertEqual(u.current_version(), self.v1)
        self.assertIn(m["version"], u.state()["bad"])
        self.assertEqual(self.restarts, 2)  # применили + вернули
        self.assertIn("ранее откатана", self.upd().check_and_apply()["note"])

    def test_pending_blocks_next_update_until_commit(self):
        d, m = self.serve(files_extra={"playbooks.py": "X = 4\n"})
        self.upd().check_and_apply(restart=None)  # применено без проверки: pending остался (как при execv)
        u = updater.Updater("x", self.inst)
        self.assertIsNotNone(u.state()["pending"])
        self.assertIn("не подтверждено", self.upd().check_and_apply()["note"])
        self.assertFalse(updater.commit_if_healthy(self.inst, m["version"], 1))
        self.assertTrue(updater.commit_if_healthy(self.inst, m["version"], 3))
        self.assertIsNone(u.state()["pending"])
        self.assertFalse(updater.commit_if_healthy(self.inst, "other", 9))

    def test_unreachable_server_is_not_fatal(self):
        u = updater.Updater("http://127.0.0.1:1", self.inst)
        r = u.check_and_apply()
        self.assertFalse(r["ok"])
        self.assertEqual(u.current_version(), self.v1)

    def test_manual_rollback(self):
        d, m = self.serve(files_extra={"playbooks.py": "X = 5\n"})
        self.upd().check_and_apply(restart=self.restart, health=lambda v: True)
        u = updater.Updater("x", self.inst)
        self.assertEqual(u.rollback("тест"), self.v1)
        self.assertEqual(u.current_version(), self.v1)


# ---------------------------------------------------------------- watchdog (bash)
class TestWatchdog(unittest.TestCase):
    def setUp(self):
        self.h = tempfile.mkdtemp(prefix="dsp_wd_")
        for d in ("run", "logs", "dsp/releases/r1", "dsp/releases/r2"):
            os.makedirs(os.path.join(self.h, d))
        os.symlink("releases/r2", self.h + "/dsp/current")
        os.symlink("releases/r1", self.h + "/dsp/previous")
        self.disp = self.h + "/fake_disp.sh"
        open(self.disp, "w").write('#!/bin/bash\nH=%s\npython3 -I -c \'import json,os,time,sys;json.dump({"ts":time.time(),"pid":os.getppid()},open(sys.argv[1],"w"))\' $H/run/dsp_dispatcher.hb\nsleep 20\n' % self.h)
        self.env = dict(os.environ, DSP_HOME=self.h, DSP_RUN_CMD="bash " + self.disp, DSP_STOP_FILES=self.h + "/STOP", DSP_FALLBACK=self.h + "/fallback.sh", DSP_STALE_S="90")
        self.procs = []

    def tearDown(self):
        subprocess.run(["pkill", "-f", self.disp], check=False)
        shutil.rmtree(self.h, ignore_errors=True)

    def wd(self, *args, env=None):
        return subprocess.run(["bash", os.path.join(HERE, "watchdog.sh")] + list(args), env=env or self.env, capture_output=True, text=True, timeout=30)

    def wait(self, path, t=5):
        end = time.time() + t
        while time.time() < end:
            if os.path.exists(path):
                return True
            time.sleep(0.1)
        return False

    def test_starts_dispatcher_when_no_heartbeat_and_not_twice(self):
        r = self.wd()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.wait(self.h + "/run/dsp_dispatcher.hb"))
        self.assertTrue(os.path.exists(self.h + "/run/dsp_watchdog.hb"))
        before = open(self.h + "/run/dsp_wd_starts").read().count("\n")
        self.wd()
        self.assertEqual(open(self.h + "/run/dsp_wd_starts").read().count("\n"), before)  # живой - не трогает

    def test_stop_file_does_not_prevent_dispatcher_but_blocks_fallback(self):
        open(self.h + "/STOP", "w").write("1")
        os.remove(self.h + "/dsp/previous")
        open(self.h + "/fallback.sh", "w").write("#!/bin/bash\ntouch %s/fallback_ran\n" % self.h)
        env = dict(self.env, DSP_RUN_CMD="false")
        for _ in range(5):
            self.wd(env=env)
        self.assertFalse(self.wait(self.h + "/fallback_ran", 1.5))
        self.assertEqual(self.wd().returncode, 0)
        self.assertTrue(self.wait(self.h + "/run/dsp_dispatcher.hb"))

    def test_rollback_on_expired_pending(self):
        json.dump({"bad": [], "history": [], "pending": {"version": "r2", "prev": "r1", "deadline": time.time() - 5}}, open(self.h + "/dsp/updates.json", "w"))
        self.wd()
        self.assertEqual(os.readlink(self.h + "/dsp/current"), "releases/r1")
        st = json.load(open(self.h + "/dsp/updates.json"))
        self.assertIn("r2", st["bad"])
        self.assertIsNone(st["pending"])

    def test_pending_not_expired_keeps_release(self):
        json.dump({"bad": [], "history": [], "pending": {"version": "r2", "prev": "r1", "deadline": time.time() + 500}}, open(self.h + "/dsp/updates.json", "w"))
        self.wd()
        self.assertEqual(os.readlink(self.h + "/dsp/current"), "releases/r2")

    def test_rollback_after_three_failed_starts(self):
        env = dict(self.env, DSP_RUN_CMD="false")
        for _ in range(5):
            self.wd(env=env)
        self.assertEqual(os.readlink(self.h + "/dsp/current"), "releases/r1")
        self.assertIn("r2", json.load(open(self.h + "/dsp/updates.json"))["bad"])

    def test_fallback_boot_when_no_previous(self):
        os.remove(self.h + "/dsp/previous")
        open(self.h + "/fallback.sh", "w").write("#!/bin/bash\ntouch %s/fallback_ran\n" % self.h)
        env = dict(self.env, DSP_RUN_CMD="false")
        for _ in range(5):
            self.wd(env=env)
        self.assertTrue(self.wait(self.h + "/fallback_ran", 4))

    def test_dry_run_changes_nothing(self):
        r = self.wd("--dry-run")
        self.assertIn("запуск диспетчера", r.stdout)
        self.assertFalse(os.path.exists(self.h + "/run/dsp_dispatcher.hb"))
        self.assertFalse(os.path.exists(self.h + "/run/dsp_watchdog.hb"))

    def test_bad_flag(self):
        self.assertEqual(self.wd("--nope").returncode, 2)


class TestMutualWatch(Base):
    def test_dispatcher_revives_stale_watchdog(self):
        calls = []
        d = self.disp([], hooks={"ensure_watchdog": lambda: calls.append(1) or "ok"})
        d.tick()
        self.assertEqual(len(calls), 1)
        d.tick()
        self.assertEqual(len(calls), 1)  # не чаще раза в 5 мин
        self.clock.adv(400)
        json.dump({"ts": self.clock()}, open(d.paths["wd_hb"], "w"))
        d.tick()
        self.assertEqual(len(calls), 1)  # сторож свежий - не трогаем
        self.clock.adv(400)
        d.tick()
        self.assertEqual(len(calls), 2)

    def test_heartbeat_is_written_for_watchdog(self):
        d = self.disp([])
        d.tick()
        hb = json.load(open(d.paths["hb"]))
        self.assertEqual(hb["pid"], os.getpid())
        self.assertAlmostEqual(hb["ts"], self.clock(), delta=1)


class TestPingAndInstall(unittest.TestCase):
    def test_ping_decide(self):
        import dsp_ping
        run = {"actual_status": "running", "ports": {"22/tcp": [{"HostPort": "62281"}]}}
        self.assertEqual(dsp_ping.decide(run)["action"], "ssh")
        self.assertEqual(dsp_ping.decide(run)["ports"], [62281])
        self.assertEqual(dsp_ping.decide({"actual_status": "exited", "status_msg": "x"})["action"], "start")
        self.assertEqual(dsp_ping.decide({"actual_status": "loading", "cur_state": "running"})["action"], "alert")
        self.assertEqual(dsp_ping.decide({"actual_status": "running", "ports": {}})["action"], "alert")
        self.assertNotIn("github_pat_abc123", dsp_ping.mask("x github_pat_abc123 y"))

    def test_install_dry_run_writes_nothing_and_checks_syntax(self):
        t = tempfile.mkdtemp()
        try:
            env = dict(os.environ, DSP_HOME=t, DSP_ONSTART=t + "/onstart.sh")
            r = subprocess.run(["bash", os.path.join(HERE, "install_dsp_s1.sh"), "--dry-run", "--start", "--systemd"], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("[dry-run]", r.stdout)
            self.assertIn("DSP-02.json", r.stdout)
            self.assertEqual(os.listdir(t), [])
            self.assertEqual(subprocess.run(["bash", os.path.join(HERE, "install_dsp_s1.sh"), "--bad"], capture_output=True).returncode, 2)
        finally:
            shutil.rmtree(t)

    def test_shell_scripts_syntax(self):
        for f in ("watchdog.sh", "install_dsp_s1.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", os.path.join(HERE, f)]).returncode, 0, f)

    def test_manifest_excludes_docs_and_is_consistent(self):
        m = updater.make_manifest(HERE)
        self.assertNotIn("CARDS.md", m["files"])
        self.assertEqual(m["version"], updater.version_of(m["files"]))
        for r in updater.REQUIRED:
            self.assertIn(r, m["files"])


if __name__ == "__main__":
    unittest.main()
