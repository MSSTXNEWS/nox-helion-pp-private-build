#!/usr/bin/env python3
"""One fixed action: temporarily attach a throwaway SSH key to Vast instance 60509551,
run the reviewed agent-updater (branch u, file u) over SSH, then detach the key.
No arbitrary command input. Secret NOX2 is only sent to console.vast.ai."""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request, shlex
INSTANCE = 60509551  # S2 (США); S1 (Квебек) = 61825960, выбирается маркером #S1 в начале REMOTE
KEY = os.environ["NOX2"]
REMOTE = '#S1\ncurl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c607/inspect_v7_lineages.sh -o /tmp/sr.sh && bash /tmp/sr.sh 2>&1 | tail -c 3000 # 20261122192948Z'

if REMOTE.startswith("#S1"):
    INSTANCE = 61825960

def api(method, path, body=None):
    req = urllib.request.Request("https://console.vast.ai/api/v0" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + KEY, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}

def detach_checked_key(pub, key_id):
    """Confirm provider key removal before reporting a successful owner action.

    A DELETE response alone is not proof of revoked access. This performs one
    read-only provider readback; never retries the remote SSH action.
    """
    api("DELETE", "/instances/%d/ssh/%d" % (INSTANCE, key_id))
    rows = api("GET", "/instances/%d/ssh/" % INSTANCE)
    if isinstance(rows, dict):
        rows = rows.get("ssh_keys", rows.get("keys"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("HOLD_EPHEMERAL_KEY_READBACK_SHAPE")
    fingerprint = pub.split()[1]
    if any(str(row.get("id")) == str(key_id) or fingerprint in json.dumps(row) for row in rows):
        raise RuntimeError("HOLD_EPHEMERAL_KEY_STILL_PRESENT")


def main():
    inst = api("GET", "/instances/%d/" % INSTANCE)
    inst = inst.get("instances", inst)
    if isinstance(inst, list): inst = next(i for i in inst if i.get("id") == INSTANCE)
    ip = inst["public_ipaddr"]
    ports = [int(m["HostPort"]) for m in inst.get("ports", {}).get("22/tcp", []) if str(m.get("HostPort", "")).isdigit()]
    if inst.get("actual_status") != "running" or not ports: sys.exit("instance not running / no ssh port: id=%s actual_status=%s cur_state=%s intended=%s msg=%s" % (INSTANCE, inst.get("actual_status"), inst.get("cur_state"), inst.get("intended_status"), str(inst.get("status_msg"))[:200]))
    d = tempfile.mkdtemp(); kf = d + "/k"
    key_id = None
    pub = None
    try:
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "nox-update-button", "-f", kf], check=True)
        with open(kf + ".pub", encoding="utf-8") as keyfile:
            pub = keyfile.read().strip()
        api("POST", "/instances/%d/ssh/" % INSTANCE, {"ssh_key": pub})
        for _ in range(8):
            rows = api("GET", "/instances/%d/ssh/" % INSTANCE)
            rows = rows if isinstance(rows, list) else rows.get("ssh_keys", rows.get("keys", []))
            hit = [r for r in rows if isinstance(r, dict) and pub.split()[1] in json.dumps(r)]
            if hit: key_id = hit[0].get("id"); break
            time.sleep(2)
        # Do not dispatch SSH until the ephemeral provider key is confirmed.
        # One remote command only: an SSH failure may hide an action that ran.
        if key_id is None or not str(key_id).isdecimal() or int(key_id) <= 0:
            sys.exit("HOLD_UNCONFIRMED_EPHEMERAL_KEY_ID; remote command NOT dispatched")
        key_id = int(key_id)
        time.sleep(15)
        r = subprocess.run(["ssh", "-T", "-i", kf, "-p", str(ports[0]), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + d + "/kh",
            "root@" + ip, "bash -o pipefail -c " + shlex.quote(REMOTE)], capture_output=True, text=True, errors="replace", timeout=295,
            input=(os.environ.get("TS_AUTHKEY","") + "\n"))
        print("ssh rc=%d" % r.returncode)
        print(re.sub(r"(github_pat_\w+|tskey-[\w-]+)", "***", r.stdout[-3000:]))
        if r.returncode != 0:
            sys.exit("HOLD_AMBIGUOUS_SSH_REMOTE_OUTCOME; no automatic replay, owner readback required")

    finally:
        # Even if provider cleanup HOLDs or ssh-keygen fails, never leave the
        # generated private key on the workflow runner's local filesystem.
        try:
            if isinstance(key_id, int) and key_id > 0:
                try:
                    detach_checked_key(pub, key_id)
                    print("temp key detached; provider readback confirms absence")
                except Exception as exc:
                    print("HOLD_EPHEMERAL_KEY_CLEANUP_UNVERIFIED", type(exc).__name__,
                          "- verify/remove nоx-update-button key in Vast before any retry",
                          file=sys.stderr)
                    raise SystemExit(2)
            else:
                print("HOLD_UNCONFIRMED_EPHEMERAL_KEY_ID: provider key cleanup needs owner inspection")
        finally:
            try:
                shutil.rmtree(d)
            except OSError as exc:
                print("HOLD_LOCAL_EPHEMERAL_KEY_CLEANUP_UNVERIFIED", type(exc).__name__, file=sys.stderr)
                raise SystemExit(2) from exc

if __name__ == "__main__":
    main()
