#!/usr/bin/env python3
"""One fixed action: temporarily attach a throwaway SSH key to Vast instance 60509551,
run the reviewed agent-updater (branch u, file u) over SSH, then detach the key.
No arbitrary command input. Secret NOX2 is only sent to console.vast.ai."""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
INSTANCE = 60509551
KEY = os.environ["NOX2"]
REMOTE = (
    "set -eu; f=$(mktemp /tmp/nox-web-deploy.XXXXXX); "
    "trap 'rm -f \"$f\"' EXIT; "
    "curl -fsSL --retry 2 --max-time 45 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/6553525b18673fe86183e033e972c67869fab2f8/nox-control/cmd_agent/deploy_web.sh' -o \"$f\"; "
    "printf '%s  %s\\n' 'd945cb215b81ec5e40f2c002e148707eba605c3021cdec112f7aa704d5d50e75' \"$f\" | sha256sum -c - >/dev/null; "
    "bash \"$f\" '3722bd72d368501cfd5c788c14df93ad097daf71779c4310cc74561f3b3979e0' 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/da3bdaaa5de10172a5b19afffc6268e9ef96a306/nox-web.part00' 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/da3bdaaa5de10172a5b19afffc6268e9ef96a306/nox-web.part01' 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/da3bdaaa5de10172a5b19afffc6268e9ef96a306/nox-web.part02'"
)

def api(method, path, body=None):
    req = urllib.request.Request("https://console.vast.ai/api/v0" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + KEY, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}

def ssh_rows():
    rows = api("GET", "/instances/%d/ssh/" % INSTANCE)
    if isinstance(rows, dict):
        rows = rows.get("ssh_keys", rows.get("keys", []))
    if not isinstance(rows, list):
        raise RuntimeError("HOLD_TEMP_KEY_LIST_CONTRACT")
    return rows


def exact_key_rows(pub):
    needle = pub.split()[1]
    return [row for row in ssh_rows()
            if isinstance(row, dict) and needle in json.dumps(row)]


def report_deploy(stdout):
    """Only fixed, non-secret fields may enter the public Actions log."""
    completed = False
    for raw in stdout.splitlines():
        line = raw.strip()
        if line == "UP_TO_DATE " + ARCHIVE_SHA:
            print("web_deploy=UP_TO_DATE")
            completed = True
        elif line == "DEPLOYED sha=" + ARCHIVE_SHA + " web=200":
            print("web_deploy=DEPLOYED_WEB_200")
            completed = True
        elif line.startswith("DEPLOYED sha=" + ARCHIVE_SHA + " web="):
            print("web_deploy=HOLD_WEB_NOT_200")
        elif line.startswith(("NO_SPACE", "SHA_MISMATCH", "DOWNLOAD_FAILED",
                              "UNPACK_FAILED", "NO_INDEX_HTML", "SWITCH_FAILED")):
            print("web_deploy=HOLD_" + line.split()[0])
        elif line.startswith("{"):
            try:
                info = json.loads(line)
                if info.get("service") == "nox-bridge":
                    print("bridge_model_alive=" + str(info.get("model_alive") is True).lower())
            except (TypeError, ValueError, AttributeError):
                pass
    return completed


def main():
    inst = api("GET", "/instances/%d/" % INSTANCE)
    inst = inst.get("instances", inst)
    if isinstance(inst, list):
        inst = next(i for i in inst if i.get("id") == INSTANCE)
    ip = inst["public_ipaddr"]
    ports = [int(m["HostPort"]) for m in inst.get("ports", {}).get("22/tcp", [])
             if str(m.get("HostPort", "")).isdigit()]
    if inst.get("actual_status") != "running" or not ports:
        sys.exit("instance not running / no ssh port")

    d = tempfile.mkdtemp(prefix="nox-owner-key-")
    kf = d + "/k"
    pub = None
    attach_attempted = False
    key_id = None
    detached = False
    try:
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
                        "nox-update-button", "-f", kf], check=True)
        with open(kf + ".pub", encoding="utf-8") as fh:
            pub = fh.read().strip()
        attach_attempted = True
        api("POST", "/instances/%d/ssh/" % INSTANCE, {"ssh_key": pub})
        for _ in range(8):
            matching = exact_key_rows(pub)
            if matching:
                key_id = matching[0].get("id")
                break
            time.sleep(2)
        if key_id is None:
            raise RuntimeError("HOLD_TEMP_KEY_ID_UNVERIFIED")

        time.sleep(15)
        for port in ports:
            for attempt in range(3):
                r = subprocess.run(["ssh", "-T", "-i", kf, "-p", str(port), "-o",
                                    "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                                    "-o", "ConnectTimeout=15", "-o",
                                    "StrictHostKeyChecking=accept-new", "-o",
                                    "UserKnownHostsFile=" + d + "/kh",
                                    "root@" + ip, REMOTE],
                                   stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, errors="replace", timeout=295)
                print("ssh_rc=%d" % r.returncode)
                completed = report_deploy(r.stdout)
                if r.returncode == 0 and completed:
                    return
                time.sleep(10)
        raise RuntimeError("HOLD_OWNER_WEB_DEPLOY_FAILED_OR_UNVERIFIED")
    finally:
        try:
            if attach_attempted and pub:
                # Resolve even when the original attach/list reply was delayed.
                for attempt in range(4):
                    try:
                        matching = exact_key_rows(pub)
                        if not matching and key_id is not None:
                            detached = True
                            break
                        for row in matching:
                            candidate_id = row.get("id")
                            if candidate_id is not None:
                                api("DELETE", "/instances/%d/ssh/%s" %
                                    (INSTANCE, candidate_id))
                        if key_id is None and matching:
                            key_id = matching[0].get("id")
                    except Exception:
                        pass  # Retry; never report detach without an exact GET.
                    time.sleep(2)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        if attach_attempted and not detached:
            raise RuntimeError("HOLD_TEMP_KEY_DETACH_UNVERIFIED")


ARCHIVE_SHA = "3722bd72d368501cfd5c788c14df93ad097daf71779c4310cc74561f3b3979e0"

if __name__ == "__main__":
    main()
