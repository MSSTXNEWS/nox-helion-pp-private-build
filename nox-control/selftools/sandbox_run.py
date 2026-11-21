"""sandbox_run: run a command in a throwaway dir with rlimits, scrubbed env, no network when possible."""
import os
import resource
import shutil
import subprocess
import tempfile
import registry as R

ALLOWED = {"python3", "node", "bash", "sh"}


@R.register("sandbox_run", "danger", {"properties": {
    "cmd": {"type": "array"}, "files": {"type": "object"}, "timeout": {"type": "integer", "default": 20},
    "mem_mb": {"type": "integer", "default": 512}, "net": {"type": "boolean", "default": False}}, "required": ["cmd"]},
    "Execute code in temp dir (files written there), CPU/mem/proc rlimits, env scrubbed, `unshare -n` if available. Needs confirm.")
def sandbox_run(a):
    cmd = a["cmd"]
    if not cmd or not all(isinstance(x, str) for x in cmd) or os.path.basename(cmd[0]) not in ALLOWED:
        raise R.Denied("sandbox cmd must start with one of %s" % sorted(ALLOWED))
    exe = shutil.which(cmd[0])
    if not exe:
        return R.blocked("%s not installed" % cmd[0], "install " + cmd[0])
    tmp = tempfile.mkdtemp(prefix="nox_sbx_")
    try:
        for name, content in (a.get("files") or {}).items():
            fp = os.path.realpath(os.path.join(tmp, name))
            if not fp.startswith(tmp + os.sep) or not isinstance(content, str):
                raise R.Denied("bad sandbox file name: " + name)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            open(fp, "w", encoding="utf-8").write(content)
        argv = [exe] + cmd[1:]
        isolated = False
        if not a["net"] and shutil.which("unshare"):
            probe = subprocess.run(["unshare", "-n", "true"], capture_output=True)
            if probe.returncode == 0:
                argv, isolated = ["unshare", "-n"] + argv, True
        mem = a["mem_mb"] << 20

        def limits():
            resource.setrlimit(resource.RLIMIT_CPU, (a["timeout"] + 2, a["timeout"] + 2))
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))
            resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except (ValueError, OSError):
                pass
            os.setsid()
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": tmp, "LANG": "C.UTF-8"}
        try:
            p = subprocess.run(argv, cwd=tmp, env=env, capture_output=True, text=True,
                               timeout=a["timeout"], preexec_fn=limits)
            return {"ok": p.returncode == 0, "rc": p.returncode, "stdout": p.stdout[-8000:],
                    "stderr": p.stderr[-4000:], "net_isolated": isolated}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout after %ds" % a["timeout"], "net_isolated": isolated}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
