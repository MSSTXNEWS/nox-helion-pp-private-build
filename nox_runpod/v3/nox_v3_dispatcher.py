#!/usr/bin/env python3
"""NOX PRIME V3 bounded orchestration. Every invocation is safe to repeat.

One controller per node. Plan mode 'prepare_no_forced_cutover' does not
start compute. 'active' runs one bounded step at a time; no force kill,
no memory deletion, no model fabrication, and no GPU double ownership.
"""
from __future__ import annotations
import argparse, datetime, fcntl, json, os, pathlib, subprocess, sys, time, shutil, urllib.request

ROOT=pathlib.Path("/workspace/nox")
STATE=ROOT/"dispatcher/nox_v3"
BIN=STATE/"bin"
PLAN=STATE/"NOX_PRIME_V3_PLAN.json"
PY=ROOT/"prime9b-venv/bin/python"
DISTILL=BIN/"a40_full_parameter_distill_cycle.py"
MEM=ROOT/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
A40_TRAIN=ROOT/"dispatcher/a40_full_parameter/progress.json"
MASTER_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox_runpod/control/NOX_MASTER_CONTROL.json"
def check_github_master():
    req=urllib.request.Request(MASTER_URL,headers={"User-Agent":"NOX-PRIME-V3/1"})
    with urllib.request.urlopen(req,timeout=18) as f:
        data=f.read(32769)
    if len(data)>32768:raise RuntimeError("MASTER_TOO_LARGE")
    doc=json.loads(data)
    if (doc.get("schema")!="nox-control-v1" or doc.get("no_loss") is not True or
        doc.get("allow_remote_delete") is not False or doc.get("allow_arbitrary_shell") is not False):
        raise RuntimeError("MASTER_UNSAFE")
    return doc["revision"]

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def emit(obj):
    obj={"utc":utc(),**obj}
    STATE.mkdir(parents=True,exist_ok=True)
    path=STATE/("orchestrator_status_"+str(obj.get("node","UNKNOWN"))+".json")
    tmp=path.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    print(json.dumps(obj,ensure_ascii=False),flush=True)
def process_has(name):
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdigit():continue
        try:
            args=[x.decode(errors="replace") for x in (p/"cmdline").read_bytes().split(bytes([0])) if x]
            if any(pathlib.Path(a).name==name for a in args[1:]):return True
        except (OSError,ValueError):pass
    return False
def launch(argv, timeout, label):
    log=ROOT/"logs"/("NOX_V3_"+label+".log")
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open("ab") as f:
        try:
            return subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=f,
                                  stderr=subprocess.STDOUT,timeout=timeout,check=False).returncode
        except subprocess.TimeoutExpired:
            return 124
def cloud_gpu_status():
    # Observability only. NVIDIA's own hardware/driver retains protection.
    # SAFE70 remains exclusively with the local Windows AMD Hot Spot monitor.
    try:
        p=subprocess.run(["nvidia-smi","--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.free",
            "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=10)
        if p.returncode:return {"status":"TELEMETRY_UNAVAILABLE"}
        a=[v.strip() for v in p.stdout.splitlines()[0].split(",")]
        return {"status":"OK","temp_core_c":int(a[0]),"util_pct":int(a[1]),
                "used_mib":int(a[2]),"free_mib":int(a[3])}
    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):
        return {"status":"TELEMETRY_UNAVAILABLE"}
def manual_stop(node):
    return (STATE/("MANUAL_STOP_"+node)).exists() or (STATE/("STOP_"+node)).exists()
def run(node,plan):
    if manual_stop(node):
        return emit({"node":node,"status":"HOLD_MANUAL_STOP"})
    mode=plan.get("mode")
    if mode not in ("prepare_no_forced_cutover","active","hold"):
        return emit({"node":node,"status":"HOLD_INVALID_MODE"})
    # Per-node savepoint and GPU ownership is recorded by the cutover agent.
    # A shared plan must never activate a machine before its own cutover receipt.
    receipt=STATE/("cutover_"+node+".json")
    try: gate=json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError,ValueError):gate={}
    active=gate.get("status")=="CUTOVER_READY" and gate.get("node")==node and gate.get("known_processes_exited") is True and gate.get("gpu_unowned") is True
    if not active:
        return emit({"node":node,"status":"HOLD_CUTOVER_SAVEPOINT_PENDING","plan_mode":mode})
    if mode=="hold":
        return emit({"node":node,"status":"HOLD_BY_MASTER_POLICY"})
    if node=="A5000":
        swarm=BIN/"nox_adaptive_swarm.py"
        if swarm.is_file():
            launch(["python3",str(swarm),"--node","A5000"],150,"SWARM_A5000")
        importer=BIN/"nox_stage_27b_to_shared.py"
        self_model=BIN/"nox_self_model.py"
        progress=BIN/"nox_progress_v3.py"
        if not importer.is_file() or not self_model.is_file():
            return emit({"node":node,"status":"HOLD_IMPORTER_OR_SELF_MODEL_MISSING"})
        rc=launch(["python3",str(importer)],1800,"27B_STAGE")
        self_rc=launch(["python3",str(self_model)],120,"SELF_MODEL")
        prog_rc=launch(["python3",str(progress)],120,"PROGRESS") if progress.is_file() else 2
        improvement=BIN/"nox_improvement_loop.py"
        journal_rc=launch(["python3",str(improvement)],120,"IMPROVEMENT") if improvement.is_file() else 2
        return emit({"node":node,"task":"27b_stage_s03_self_model_improvement","status":"DONE" if rc==0 and self_rc==0 and prog_rc==0 and journal_rc==0 else "PARTIAL",
                     "model_stage_rc":rc,"self_model_rc":self_rc,"progress_rc":prog_rc,"journal_rc":journal_rc})
    if node!="A40":
        return emit({"node":node,"status":"HOLD_NODE_UNKNOWN"})
    if process_has("a40_cuda_distillation_direct.py") or process_has("a40_full_parameter_distill_cycle.py"):
        return emit({"node":node,"status":"HOLD_OLD_OR_FULL_GPU_OWNER_ACTIVE"})
    if not MEM.is_file():
        return emit({"node":node,"status":"HOLD_S03_MEMORY_MISSING"})
    gpu=BIN/"nox_teacher_server_batch.py"
    progress=BIN/"nox_progress_v3.py"
    if not gpu.is_file() or not progress.is_file():
        return emit({"node":node,"status":"HOLD_V3_BINARIES_MISSING"})
    out={}
    # Adaptive order: do not spend every cycle on the teacher whose quota is
    # already complete, unless both teacher task sets are complete.
    metrics=STATE/"status.json"
    try: current=json.loads(metrics.read_text()).get("teachers",{})
    except (OSError,ValueError):current={}
    priority=sorted(("Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B"),
        key=lambda teacher: (current.get(teacher,{}).get("task_generation_percent") or 0,teacher))
    for teacher in priority:
        if manual_stop(node):return emit({"node":node,"status":"HOLD_SAFE70","teachers":out})
        model=ROOT/("teachers/Qwen3.5-27B/Qwen3.5-27B-Q4_K_M.gguf" if teacher=="Qwen3.5-27B"
                    else "teachers/DeepSeek-R1-Distill-Qwen-32B/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf")
        if not model.is_file():
            out[teacher]="HOLD_MODEL_NOT_READY"
            continue
        if current.get(teacher,{}).get("task_generation_percent")==100:
            out[teacher]="PLAN_TASK_SET_COMPLETE"
            continue
        
        rc=launch(["python3",str(gpu),"--teacher",teacher,"--limit","10"],5400,
                  "TEACHER_"+("27B" if teacher=="Qwen3.5-27B" else "32B"))
        out[teacher]="BATCH_DONE" if rc==0 else "HOLD_EXIT_"+str(rc)
    importer=BIN/"nox_teacher_s03_import.py"
    if importer.is_file():
        import_rc=launch(["python3",str(importer)],360,"S03_TEACHER_IMPORT")
        out["s03_import"]="COMMITTED" if import_rc==0 else "HOLD_EXIT_"+str(import_rc)
    else:
        out["s03_import"]="HOLD_IMPORTER_MISSING"
    launch(["python3",str(progress)],300,"PROGRESS")
    improvement=BIN/"nox_improvement_loop.py"
    if improvement.is_file():launch(["python3",str(improvement)],120,"IMPROVEMENT")
    # Training runs after teachers have exited. It is not started if the already
    # running legacy process came back, or if the last cycle is still in flight.
    if process_has("a40_cuda_distillation_direct.py") or process_has("a40_full_parameter_distill_cycle.py"):
        return emit({"node":node,"status":"HOLD_GPU_REOCCUPIED","teachers":out})
    if manual_stop(node):return emit({"node":node,"status":"HOLD_SAFE70_BEFORE_TRAINING","teachers":out})
    swarm=BIN/"nox_adaptive_swarm.py"
    if swarm.is_file():
        launch(["python3",str(swarm),"--node","A40"],150,"SWARM_A40")
    if not PY.is_file() or not DISTILL.is_file():
        return emit({"node":node,"status":"HOLD_STUDENT_TRAINER_MISSING","teachers":out})
    if not A40_TRAIN.parent.is_dir():
        A40_TRAIN.parent.mkdir(parents=True,exist_ok=True)
    cycle="v3_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    # The trainer owns VRAM, RAM, dataset quality, checkpoint, and holdout gates.
    rc=launch([str(PY),"-u",str(DISTILL),"--cycle",cycle,"--steps","20"],7200,"FULL_PARAMETER")
    try:
        result=json.loads(A40_TRAIN.read_text())
        status=result.get("status","UNKNOWN")
        steps=result.get("steps_executed_this_cycle",0)
    except (OSError,ValueError):
        status="UNKNOWN";steps=0
    if improvement.is_file():launch(["python3",str(improvement)],120,"IMPROVEMENT")
    emit({"node":node,"status":"COMPLETE_VERIFIED" if status=="COMPLETE_VERIFIED" and rc==0 else "HOLD",
          "teacher_batches":out,"cycle":cycle,"optimizer_steps":steps,"trainer_status":status,"exit_code":rc})
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--node",required=True,choices=("A40","A5000"))
    ap.add_argument("--once",action="store_true")
    args=ap.parse_args()
    STATE.mkdir(parents=True,exist_ok=True)
    lk=(STATE/("dispatcher_"+args.node+".lock")).open("a+")
    try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print("NOX_V3_DISPATCHER_ALREADY_RUNNING",args.node,flush=True);return
    while True:
        try:
            github_revision=check_github_master()
            plan=json.loads(PLAN.read_text())
            if plan.get("schema")!="nox-prime-v3" or plan.get("transition",{}).get("no_loss") is not True:
                raise RuntimeError("UNSAFE_OR_INVALID_PLAN")
            run(args.node,plan)
        except Exception as e:
            emit({"node":args.node,"status":"HOLD_EXCEPTION","reason":type(e).__name__+":"+str(e)[:180]})
        if args.once:return
        time.sleep(180)
if __name__=="__main__":main()
