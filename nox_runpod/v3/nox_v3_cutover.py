#!/usr/bin/env python3
"""Request safe save-point handoff from exact known old GPU workers.

Never kills in-flight GPU training, wipes weights or terminates RunPod Pods.
After known older workers exit, mark local V3 plan active. Unknown owners -> HOLD.
"""
import argparse, datetime, json, os, pathlib, subprocess, sys, time
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/nox_v3"
P=S/"NOX_PRIME_V3_PLAN.json"
STOP={
 "A40":[R/"dispatcher/a40_direct/STOP"],
 "A5000":[R/"dispatcher/a5000_cuda_secondary/STOP"],
}
KNOWN={
 "A40":{"a40_cuda_distillation_direct.py","a40_full_parameter_distill_cycle.py"},
 "A5000":{"a5000_cuda_secondary_direct.py","a5000_cuda_distillation_direct.py"}
}
def processes():
    result=[]
    for proc in pathlib.Path("/proc").iterdir():
        if not proc.name.isdigit():continue
        try:
            args=[v.decode(errors="replace") for v in (proc/"cmdline").read_bytes().split(bytes([0])) if v]
            if not args:continue
            result.append((int(proc.name),args))
        except (OSError,ValueError):pass
    return result
def gpu_pids():
    try:
        o=subprocess.run(["nvidia-smi","--query-compute-apps=pid",
           "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=12)
        if o.returncode:return None
        return {int(s.strip()) for s in o.stdout.splitlines() if s.strip().isdigit()}
    except (OSError,subprocess.TimeoutExpired):return None
def write(path,data):
    tmp=path.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--node",choices=("A40","A5000"),required=True)
    args=a.parse_args()
    node=args.node
    if not P.is_file():raise SystemExit("HOLD_V3_PLAN_MISSING")
    data=json.loads(P.read_text())
    if data.get("transition",{}).get("no_loss") is not True:
        raise SystemExit("HOLD_PLAN_NOT_NO_LOSS")
    S.mkdir(parents=True,exist_ok=True)
    for marker in STOP[node]:
        marker.parent.mkdir(parents=True,exist_ok=True)
        marker.touch()
    # Savepoint-aware handlers have one current example to finish. We do not kill them.
    active=[]
    for pid,argv in processes():
        matches=[x for x in KNOWN[node] if any(pathlib.Path(t).name==x for t in argv[1:])]
        if matches:active.append((pid,matches))
    if active:
        print("HOLD_WAIT_FOR_SAVEPOINT",active,flush=True);return 2
    owners=gpu_pids()
    if owners is None:print("HOLD_GPU_OWNER_UNAVAILABLE",flush=True);return 2
    if owners:
        print("HOLD_GPU_OWNERS_UNRECONCILED",sorted(owners),flush=True);return 2
    # Disable only *known* exact legacy supervisor jobs; unknown starters must
    # be reconciled separately instead of blindly disabled.
    if node=="A40":
        supervisor=R/"dispatcher/a40_direct/watchdog_supervise.sh"
    else:
        supervisor=R/"dispatcher/a5000_cuda_secondary/supervisor.sh"
    supervised=[pid for pid,argv in processes() if str(supervisor) in argv]
    if supervised:
        print("HOLD_LEGACY_SUPERVISOR_RUNNING",supervised,flush=True);return 2
    receipt={"status":"CUTOVER_READY","node":node,
       "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "known_processes_exited":True,"gpu_unowned":True,
       "in_flight_checkpoint_killed":False}
    write(S/("cutover_"+node+".json"),receipt)
    # Do not activate both Pods by rewriting a SHARED /workspace plan.
    # Every node needs its own receipt; dispatcher reads only matching node.
    print("NOX_V3_CUTOVER_READY",node,flush=True)
    return 0
if __name__=="__main__":
    sys.exit(main())
