"""NOX V60 native read-only storage state probe via existing V51 ephemeral SSH."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,subprocess,shutil,re
from pathlib import Path
print("NOX_NATIVE_V51_SSH_EXECUTED=true")
print("NATIVE_STORAGE_AUDIT_SCHEMA=NOX_V60_READONLY")
def cmd(a):
    try:
        o=subprocess.run(a,capture_output=True,text=True,timeout=12)
        return o.stdout if o.returncode==0 else ""
    except (OSError,subprocess.TimeoutExpired):return ""
for name in ("nox","workspace","ram"):
    path={"nox":"/root/nox","workspace":"/workspace","ram":"/dev/shm"}[name]
    try:
        st=os.statvfs(path)
        print("NATIVE_STORAGE_"+name.upper()+"_FREE_GIB="+str(round(st.f_bavail*st.f_frsize/2**30,2)))
        print("NATIVE_STORAGE_"+name.upper()+"_TOTAL_GIB="+str(round(st.f_blocks*st.f_frsize/2**30,2)))
    except OSError:
        print("NATIVE_STORAGE_"+name.upper()+"_AVAIL=HOLD")
for key in ("MemAvailable","MemTotal"):
    try:
        lines=Path("/proc/meminfo").read_text().splitlines()
        rows=[x for x in lines if x.startswith(key+":")]
        if rows: print("NATIVE_"+key.upper()+"_GIB="+str(round(int(rows[0].split()[1])/2**20,2)))
    except OSError:pass
g=cmd(["nvidia-smi","--query-gpu=index,memory.used,memory.free,utilization.gpu","--format=csv,noheader,nounits"])
for i,line in enumerate(g.splitlines()[:4]):
    if re.fullmatch(r"[0-9, ]{5,80}",line.strip()):
        print("NATIVE_GPU_"+str(i)+"="+line.strip())
rc=cmd(["rclone","listremotes"])
names={x.strip().rstrip(":") for x in rc.splitlines()}
print("NATIVE_RCLONE_INSTALLED="+str(bool(shutil.which("rclone"))).lower())
for name in ("noxdrive","noxr2"):
    print("NATIVE_REMOTE_"+name.upper()+"_CONFIGURED="+str(name in names).lower())
for name in ("noxdrive","noxr2"):
    for key in ("ACCESS_KEY_ID","SECRET_ACCESS_KEY"):
        print("NATIVE_"+name.upper()+"_"+key+"_ENV_PRESENT="+str(bool(os.environ.get("RCLONE_CONFIG_"+name.upper()+"_"+key))).lower())
print("NATIVE_READ_ONLY_COMPLETE=true")
PYREMOTE
"""
if __name__=="__main__":
    c.REMOTE=REMOTE
    good=False
    try:
        good=c.probe()
    except Exception as error:
        msg=str(error)
        print("NOX_NATIVE_STORAGE="+msg if msg.startswith("HOLD_") else "NOX_NATIVE_STORAGE=HOLD_CONNECTION")
    finally:
        try:
            if not c.cleanup():good=False
        except Exception:
            print("NOX_NATIVE_STORAGE=HOLD_CLEANUP")
            good=False
    raise SystemExit(0 if good else 2)
