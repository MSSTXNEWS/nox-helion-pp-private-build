#!/usr/bin/env python3
"""Внешний пинг S1 из GitHub Actions (cron). Фиксированное действие, без произвольного ввода (как cmd_agent/run_update.py).
1) Vast API: статус инстанса S1. Не running -> провал workflow (письмо владельцу); при DSP_PING_AUTOSTART=1 пробует PUT state=running (НЕ проверено на живом API, тратит баланс).
2) running -> временный SSH-ключ -> фиксированная команда: watchdog.sh --once (перезапустит диспетчер, если он мёртв) + статус диспетчера. Ключ снимается в finally.
Секреты: NOX2 (Vast API key). Токены в выводе маскируются."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

INSTANCE = 61825960  # S1 «Канада»
REMOTE = ("if [ -f /root/nox/dsp/current/watchdog.sh ]; then bash /root/nox/dsp/current/watchdog.sh --once; sleep 3; "
          "python3 /root/nox/dsp/current/nox_dispatcher.py status 2>&1 | head -c 1800; else echo DSP_NOT_INSTALLED; exit 3; fi")


def decide(inst):
    """Чистая функция: по JSON инстанса -> {'action': 'ssh'|'alert'|'start', 'why': str, 'port': int|None}."""
    st = inst.get("actual_status")
    ports = [int(m["HostPort"]) for m in (inst.get("ports") or {}).get("22/tcp", []) if str(m.get("HostPort", "")).isdigit()]
    if st == "running" and ports:
        return {"action": "ssh", "why": "инстанс running", "ports": ports}
    if st in ("exited", "stopped") or inst.get("cur_state") == "stopped":
        return {"action": "start", "why": "инстанс остановлен (actual_status=%s, msg=%s)" % (st, str(inst.get("status_msg"))[:120])}
    return {"action": "alert", "why": "инстанс не готов: actual_status=%s cur_state=%s intended=%s msg=%s" % (st, inst.get("cur_state"), inst.get("intended_status"), str(inst.get("status_msg"))[:160])}


def mask(s):
    return re.sub(r"(github_pat_\w+|tskey-[\w-]+|[A-Fa-f0-9]{40,})", "***", s)


def api(method, path, body=None, key=None):
    req = urllib.request.Request("https://console.vast.ai/api/v0" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + key, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def main():
    key = os.environ["NOX2"]
    inst = api("GET", "/instances/%d/" % INSTANCE, key=key)
    inst = inst.get("instances", inst)
    if isinstance(inst, list):
        inst = next(i for i in inst if i.get("id") == INSTANCE)
    dec = decide(inst)
    print("DSP-PING:", dec["action"], dec["why"])
    if dec["action"] == "start":
        if os.environ.get("DSP_PING_AUTOSTART") == "1":
            print(mask(json.dumps(api("PUT", "/instances/%d/" % INSTANCE, {"state": "running"}, key=key))[:300]))
        sys.exit("S1 остановлен: " + dec["why"])
    if dec["action"] == "alert":
        sys.exit(dec["why"])
    ip = inst["public_ipaddr"]
    d = tempfile.mkdtemp()
    kf = d + "/k"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "nox-dsp-ping", "-f", kf], check=True)
    pub = open(kf + ".pub").read().strip()
    key_id = None
    try:
        api("POST", "/instances/%d/ssh/" % INSTANCE, {"ssh_key": pub}, key=key)
        for _ in range(8):
            rows = api("GET", "/instances/%d/ssh/" % INSTANCE, key=key)
            rows = rows if isinstance(rows, list) else rows.get("ssh_keys", rows.get("keys", []))
            hit = [r for r in rows if isinstance(r, dict) and pub.split()[1] in json.dumps(r)]
            if hit:
                key_id = hit[0].get("id")
                break
            time.sleep(2)
        time.sleep(15)
        for port in dec["ports"]:
            for _ in range(3):
                r = subprocess.run(["ssh", "-T", "-i", kf, "-p", str(port), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
                                    "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + d + "/kh", "root@" + ip, REMOTE],
                                   capture_output=True, text=True, errors="replace", timeout=120)
                print("ssh rc=%d" % r.returncode)
                print(mask(r.stdout[-2000:]))
                if r.returncode == 0:
                    return
                if r.returncode == 3:
                    sys.exit("DSP не установлен на S1")
                time.sleep(10)
        sys.exit("ssh не удался")
    finally:
        if key_id is not None:
            try:
                api("DELETE", "/instances/%d/ssh/%s" % (INSTANCE, key_id), key=key)
                print("temp key detached")
            except Exception as e:  # noqa: BLE001
                print("DETACH FAILED", type(e).__name__, "- удалите ключ 'nox-dsp-ping' в Vast вручную")


if __name__ == "__main__":
    main()
