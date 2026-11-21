"""pc_pull: rsync over ssh from the owner's PC via Tailscale. dry-run by default (rsync -n)."""
import os
import registry as R

HOST = os.environ.get("NOX_PC_HOST", "100.84.111.36")


@R.register("pc_pull", "write", {"properties": {
    "remote_path": {"type": "string"}, "dest": {"type": "string"}, "user": {"type": "string"},
    "host": {"type": "string"}, "port": {"type": "integer", "default": 22}, "max_mb": {"type": "integer", "default": 2048},
    "identity": {"type": "string"}}, "required": ["remote_path", "dest", "user"]},
    "Pull files from PC (Tailscale 100.84.111.36) with rsync over ssh. dry_run lists transfers. Blocked without ssh access.")
def pc_pull(a):
    host = a.get("host") or HOST
    dest = R.safe_path(a["dest"])
    rp = a["remote_path"]
    if not rp.startswith(("/", "~", "C:", "c:")) or ".." in rp.split("/") or any(c in rp for c in ";|&$`\n"):
        raise R.Denied("bad remote_path")
    if not a["user"].replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise R.Denied("bad user")
    ssh = ["ssh", "-p", str(a["port"]), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new"]
    if a.get("identity"):
        ssh += ["-i", R.safe_path(a["identity"], must_exist=True, allow=[os.path.expanduser("~/.ssh"), "/root/nox"])]
    probe = R.run(ssh + ["%s@%s" % (a["user"], host), "true"], timeout=20)
    if probe.get("missing"):
        return R.blocked("ssh not installed", "install openssh-client")
    if probe["rc"] != 0:
        return R.blocked("no ssh access to PC %s: %s" % (host, probe["err"].strip()[-150:]),
                         "owner: enable OpenSSH server on PC, run Tailscale on both, add this host's public key to authorized_keys")
    cmd = ["rsync", "-a", "--partial", "--max-size=%dM" % a["max_mb"], "-e", " ".join(ssh)]
    if a["dry_run"]:
        cmd += ["-n", "-v", "--itemize-changes"]
    cmd += ["%s@%s:%s" % (a["user"], host, rp), dest + os.sep]
    if not a["dry_run"]:
        os.makedirs(dest, exist_ok=True)
    r = R.run(cmd, timeout=3600)
    if r.get("missing"):
        return R.blocked("rsync not installed", "install rsync")
    return {"ok": r["rc"] == 0, "dry_run": a["dry_run"], "rc": r["rc"], "out": r["out"][-3000:], "err": r["err"][-500:], "cmd": cmd[:4] + ["..."]}
