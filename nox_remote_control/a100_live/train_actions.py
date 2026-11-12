#!/usr/bin/env python3
"""NOX36 A100 fixed allowlist: install FAST75, stage local assets, resume safely.
No generic command execution and no shared /workspace I/O.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import urllib.request

STATE=Path("/root/.local/state/nox-a100-live-bridge")
LOCAL=Path("/tmp/nox36_local")
FAST=Path("/tmp/NOX_A100_FAST75_V2")
BASE=Path("/dev/shm/base36")
CK_SOURCE=Path("/root/nox36/ckpt/sft")
PACK_URL=("https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/"
 "0d93d440910f7f1b0ad9bf68e3b7a64fbc78b491/"
 "nox_remote_control/a100_live/assets/NOX_A100_FAST75_V2.tgz.b64")
PACK_SHA="33afe7ea74fb5cf635815f1891298e92bc54b516d5a5462beb3214a2a9d8b652"
OPS_LIMIT={"stage_fast75","prepare_local","resume_training","training_status","arm_resume_training","cancel_auto_resume"}

def safe_local(path):
    raw=str(path)
    resolved=os.path.realpath(raw)
    if raw.startswith("/workspace") or resolved.startswith("/workspace"):
        raise ValueError("HOLD_NETWORK_VOLUME")
    if not (resolved.startswith("/root/") or resolved.startswith("/tmp/") or resolved.startswith("/dev/shm/")):
        raise ValueError("HOLD_UNTRUSTED_PATH")
    return path

def stage_fast75():
    if (FAST/"START_FAST75.sh").is_file() and (FAST/"preflight.py").is_file():
        try:
            digests={
                "START_FAST75.sh":"54a74ca58ad51728954f77df836c5d1eb7b51b8b092ff731009829f4f8d5f063",
                "preflight.py":"35ba5b1193582156a6f43bb2f94f0479a4a6625524c9fb80b1058c1739ed9f27",
                "trainer/train_n36_fast75.py":"ed6886289a8666476d8365165ddfe06ff089d7018632cf775313099ed1aca307"
            }
            for name, expected in digests.items():
                if hashlib.sha256((FAST/name).read_bytes()).hexdigest()!=expected:
                    return {"state":"HOLD_PACKAGE_CHANGED","name":name}
        except OSError:return {"state":"HOLD_PACKAGE_UNREADABLE"}
        return {"state":"READY","package":"FAST75_V2","location":"LOCAL_TMP","sha256_verified":True}
    req=urllib.request.Request(PACK_URL,headers={"User-Agent":"NOX-fixed-training/1"})
    with urllib.request.urlopen(req,timeout=20) as r:
        raw=r.read(30000)
    if len(raw)>29000: return {"state":"HOLD_OVERSIZE"}
    try: data=base64.b64decode(raw,validate=True)
    except Exception: return {"state":"HOLD_ARCHIVE_BASE64"}
    if hashlib.sha256(data).hexdigest()!=PACK_SHA:
        return {"state":"HOLD_ARCHIVE_SHA256"}
    tmp=Path("/tmp/nox-fast75-stage-"+str(os.getpid()))
    if tmp.exists(): return {"state":"HOLD_STAGE_COLLISION"}
    tmp.mkdir(mode=0o700)
    try:
        with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as tf:
            members=tf.getmembers()
            if not 2<=len(members)<=40: return {"state":"HOLD_ARCHIVE_MEMBERS"}
            for m in members:
                p=Path(m.name)
                if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0]!="NOX_A100_FAST75_V2" or not (m.isfile() or m.isdir()) or m.size>200000:
                    return {"state":"HOLD_ARCHIVE_UNSAFE"}
            for m in members:
                path=tmp.joinpath(*Path(m.name).parts)
                if m.isdir(): path.mkdir(parents=True,exist_ok=True)
                else:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with tf.extractfile(m) as inp, path.open("wb") as out:
                        shutil.copyfileobj(inp,out)
        selected=tmp/"NOX_A100_FAST75_V2"
        if not (selected/"START_FAST75.sh").is_file() or not (selected/"preflight.py").is_file():
            return {"state":"HOLD_ARCHIVE_CONTENT"}
        if FAST.exists():
            return {"state":"HOLD_EXISTING_FAST75_PARTIAL"}
        selected.rename(FAST)
        return {"state":"READY","package":"FAST75_V2","sha256":PACK_SHA}
    finally:
        shutil.rmtree(tmp,ignore_errors=True)

def local_candidates():
    return [
        Path("/root/nox36/data/tok"),
        Path("/root/nox36_local/data/tok"),
        Path("/tmp/nox36_local/data/tok"),
        Path("/dev/shm/nox36/data/tok"),
        Path("/dev/shm/nox36_local/data/tok"),
    ]

def locate_data():
    for candidate in local_candidates():
        try:
            safe_local(candidate)
            a,b=candidate/"train.pt",candidate/"hold.pt"
            if a.is_file() and b.is_file() and a.stat().st_size>100 and b.stat().st_size>100:
                if all(not os.path.realpath(str(p)).startswith("/workspace") for p in (a,b)):
                    return candidate
        except (OSError,ValueError): continue
    return None

def locate_common():
    for candidate in (Path("/tmp/nox_seed_gpu"),Path("/root/nox_seed_gpu"),Path("/root/nox36/scripts"),Path("/dev/shm/nox_seed_gpu")):
        try:
            safe_local(candidate)
            if (candidate/"common.py").is_file() and not os.path.realpath(str(candidate/"common.py")).startswith("/workspace"):
                return candidate
        except (ValueError,OSError): pass
    return None

def ckpt():
    folder=CK_SOURCE/"last"
    try:
        safe_local(folder)
        s=(folder/"STEP").read_text(encoding="utf-8").strip()
        if not s.isdecimal(): return {"state":"HOLD_STEP"}
        step=int(s)
        files=("adapter_model.safetensors","opt.pt","STEP")
        sizes={}
        for name in files:
            p=folder/name
            if not p.is_file(): return {"state":"HOLD_INCOMPLETE","step":step,"missing":name}
            sizes[name]=p.stat().st_size
        if step<106 or not sizes["adapter_model.safetensors"]>100 or not sizes["opt.pt"]>100:
            return {"state":"HOLD_CHECKPOINT_STEP_OR_SIZE","step":step}
        return {"state":"LOCAL_PRESENT","step":step,"files":sizes,"sha_manifest":(folder/"SHA256SUMS").is_file(),"plan":(CK_SOURCE/"plan.json").is_file()}
    except (OSError,ValueError): return {"state":"HOLD_CKPT_UNAVAILABLE"}

def prepare_local():
    dataset=locate_data()
    source=ckpt()
    common=locate_common()
    if not dataset: return {"state":"HOLD_TRAIN_AND_HOLD_DATA_ABSENT","checkpoint":source.get("step")}
    if source.get("state")!="LOCAL_PRESENT": return source
    if not source.get("sha_manifest"):return {"state":"HOLD_NO_SHA256_MANIFEST","step":source["step"]}
    if not source.get("plan"):return {"state":"HOLD_NO_ORIGINAL_PLAN","step":source["step"]}
    if not common: return {"state":"HOLD_COMMON_CODE"}
    if not BASE.is_dir() or not (BASE/"config.json").is_file():
        return {"state":"HOLD_BASE_NOT_LOCAL"}
    try:
        for shard in BASE.glob("*.safetensors"):
            safe_local(shard)
            if not shard.is_file() or shard.stat().st_size<1000:
                return {"state":"HOLD_BASE_SHARD_NOT_LOCAL"}
    except (OSError,ValueError):return {"state":"HOLD_BASE_SHARD_INVALID"}
    LOCAL.mkdir(parents=True,exist_ok=True)
    for link,target in [
        (LOCAL/"data/tok",dataset),
        (LOCAL/"ckpt/sft/last",CK_SOURCE/"last"),
        (LOCAL/"ckpt/sft/plan.json",CK_SOURCE/"plan.json"),
        (Path("/tmp/nox_seed_gpu"),common),
    ]:
        safe_local(target)
        if link==target:continue
        if link.exists():
            if os.path.samefile(link,target):continue
            return {"state":"HOLD_STAGE_CONFLICT","name":link.name}
        link.parent.mkdir(parents=True,exist_ok=True)
        link.symlink_to(target,target_is_directory=target.is_dir())
    return {"state":"STAGED_LOCAL","step":source["step"],"data":"LOCAL_NO_NETWORK"}

def existing_trainers():
    found=[]
    for p in Path("/proc").iterdir():
        if not p.name.isdecimal():continue
        try:
            args=(p/"cmdline").read_bytes().split(b"\x00")
            names={os.path.basename(x.decode("utf-8","replace")) for x in args[1:] if x}
            if {"train_n36.py","train_n36_fast75.py"} & names:
                found.append(int(p.name))
        except OSError:continue
    return found[:12]

def training_status():
    status={"checkpoint":ckpt(),"trainer_pids":existing_trainers()}
    path=LOCAL/"status_sft.json"
    try:
        if path.is_file() and path.stat().st_size<5000:
            obj=json.loads(path.read_text())
            status["progress"]={key:obj.get(key) for key in ("step","total","loss","tok_s","eta_min") if key in obj}
    except (OSError,ValueError):pass
    try:
        p=(STATE/"training.pid")
        if p.is_file(): status["launcher_pid"]=int(p.read_text())
    except (OSError,ValueError):pass
    return status

def resume_training():
    existing=existing_trainers()
    if existing: return {"state":"HOLD_TRAINER_ALREADY_ACTIVE","pids":existing}
    if (LOCAL/"STOP_sft").exists():return {"state":"HOLD_STOP_MARKER"}
    stage=stage_fast75()
    if stage["state"]!="READY": return stage
    ready=prepare_local()
    if ready["state"]!="STAGED_LOCAL": return ready
    try:
        free=shutil.disk_usage("/").free
        if free<8*1024**3:return {"state":"HOLD_LOCAL_DISK_LT8_GIB","free_gib":round(free/1024**3,2)}
    except OSError:return {"state":"HOLD_DISK"}
    STATE.mkdir(parents=True,exist_ok=True)
    sync_armed=(Path("/root/.ssh/nox_vast").is_file()
                and Path("/root/.ssh/known_hosts").is_file()
                and shutil.which("rsync") is not None
                and (FAST/"RUN_NOW_AND_EXPORT.sh").is_file()
                and (FAST/"SYNC_ACCEPTED_CHECKPOINTS.sh").is_file())
    runfile=FAST/("RUN_NOW_AND_EXPORT.sh" if sync_armed else "START_FAST75.sh")
    if not runfile.is_file():return {"state":"HOLD_TRAINER_PACKAGE"}
    env=os.environ.copy()
    env.update({"NOX_LOCAL_ROOT":str(LOCAL),"NOX_COMMON_ROOT":str(Path("/tmp/nox_seed_gpu")),
                "BASE":str(BASE),"EXPECTED_STEP":str(ready["step"]),"MIN_RESUME_STEP":str(ready["step"]),
                "CPU_FRACTION":"0.75","MB":"8192","SAVE_MIN":"10",
                "HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1",
                "NOX_EXPORT_COMMAND":"","ENABLE_CHECKPOINT_SYNC":"1" if sync_armed else "0"})
    logfile=STATE/"train_resume_stdout.log"
    with logfile.open("ab",buffering=0) as log:
        p=subprocess.Popen(["bash",str(runfile)],cwd=str(FAST),stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True,close_fds=True)
    (STATE/"training.pid").write_text(str(p.pid))
    return {"state":"LAUNCH_REQUESTED_NOT_STEP_VERIFIED","pid":p.pid,"resume_step":ready["step"],
            "profile":"FAST75","gpu":"A100","cpu_target_pct":75,
            "nonblocking_checkpoint_sync_armed":sync_armed}

AUTO=STATE/"auto_resume.json"

def arm_resume_training():
    STATE.mkdir(parents=True,exist_ok=True)
    if AUTO.is_file():
        return {"state":"AUTO_RESUME_ALREADY_ARMED"}
    data={"created_epoch":int(time.time()),"expires_epoch":int(time.time()+6*3600)}
    temp=STATE/("auto_resume."+str(os.getpid())+".tmp")
    with temp.open("w") as f:
        json.dump(data,f);f.flush();os.fsync(f.fileno())
    os.replace(temp,AUTO)
    return {"state":"AUTO_RESUME_ARMED","hours":6,"checkpoint_min_step":106}

def cancel_auto_resume():
    AUTO.unlink(missing_ok=True)
    return {"state":"AUTO_RESUME_CANCELLED","trainer_untouched":True}

def poll_auto_resume():
    if not AUTO.is_file():return None
    try:
        conf=json.loads(AUTO.read_text())
        if time.time()>float(conf["expires_epoch"]):
            AUTO.unlink(missing_ok=True)
            return {"state":"AUTO_RESUME_EXPIRED"}
    except (OSError,ValueError,KeyError):return {"state":"HOLD_AUTO_RESUME_STATE"}
    attempt=STATE/"auto_resume_last_attempt"
    try:
        if time.time()-float(attempt.read_text())<120:return None
    except (OSError,ValueError):pass
    attempt.write_text(str(time.time()))
    if (LOCAL/"STOP_sft").exists():return {"state":"HOLD_STOP_MARKER"}
    result=resume_training()
    if result.get("state")=="LAUNCH_REQUESTED_NOT_STEP_VERIFIED":
        AUTO.unlink(missing_ok=True)
    return result

def run_operation(op):
    if op=="stage_fast75":return stage_fast75()
    if op=="prepare_local":return prepare_local()
    if op=="resume_training":return resume_training()
    if op=="training_status":return training_status()
    if op=="arm_resume_training":return arm_resume_training()
    if op=="cancel_auto_resume":return cancel_auto_resume()
    raise ValueError("OP_NOT_ALLOWED")
