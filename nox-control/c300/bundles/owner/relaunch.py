#!/usr/bin/env python3
"""K1: перезапуск процесса «как был» (argv/env/cwd из /proc). relaunch.py <pid> <logfile> [health_url]"""
import os, sys, time, signal, subprocess, urllib.request
pid = int(sys.argv[1]); logp = sys.argv[2]; url = sys.argv[3] if len(sys.argv) > 3 else None
argv = [a.decode() for a in open("/proc/%d/cmdline" % pid, "rb").read().split(b"\0") if a]
env = dict(kv.split("=", 1) for kv in open("/proc/%d/environ" % pid, "rb").read().decode("utf-8", "replace").split("\0") if "=" in kv)
cwd = os.readlink("/proc/%d/cwd" % pid)
os.kill(pid, signal.SIGTERM)
for _ in range(60):
    try: os.kill(pid, 0); time.sleep(0.5)
    except OSError: break
else:
    os.kill(pid, signal.SIGKILL); time.sleep(1)
p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=open(logp, "ab"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
print("old", pid, "new", p.pid, argv[-1][:60], flush=True)
if url:
    t0 = time.time()
    while time.time() - t0 < 90:
        try:
            r = urllib.request.urlopen(url, timeout=3); print("health", url, r.status, "%.0f с" % (time.time() - t0)); break
        except urllib.error.HTTPError as e: print("health", url, e.code, "%.0f с" % (time.time() - t0)); break
        except Exception: time.sleep(1)
    else: print("health TIMEOUT", url)
