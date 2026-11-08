"""NOX AMD SAFE70 V2. Continues LoRA adapter tensors; not optimizer state.
Only local existing Qwen2.5-0.5B, owner-approved dataset, saved checkpoints.
20-step bounded cycle, checkpoint every 5; fail closed at 70C/hotspot,
battery <=20%, 60GB reserve, sensor loss. NEVER NtSuspendProcess.
"""
from __future__ import annotations
import argparse,ctypes,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import urlopen
from nox_safe70_thermal_guard_v1 import ThermalGuard

ROOT=Path(r"C:\NOX_HELION\NOX_NEW")
SENSOR="http://127.0.0.1:8085/data.json"
LIMIT=70
RESUME_BELOW=65
COOL=180
MAX_CYCLES=2000
MAX_THERMAL_RESTARTS=24
TARGET_TOTAL_STEPS=11120

def receipt(path,payload):
    """Windows-safe telemetry: unique staging, bounded retries, sidecar fallback.

    A dashboard/antivirus/another NOX service can temporarily hold training.json
    open without FILE_SHARE_DELETE, causing os.replace -> WinError 5. A telemetry
    collision must never kill a healthy, thermally supervised LoRA worker.
    The independent SAFE70 receipt is a real event record, never fake progress.
    """
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(payload,ensure_ascii=False,indent=2)
    part=path.parent/("." + path.name + "." + str(os.getpid()) + ".tmp")
    part.write_text(raw,encoding="utf-8")
    try:
        for attempt in range(12):
            try:
                os.replace(part,path)
                return
            except PermissionError:
                time.sleep(min(.12*(attempt+1),.45))
        # Fallback own file: no contention with training.json readers/writers.
        sidecar=path.with_name("training_safe70.json")
        try:
            os.replace(part,sidecar)
            print("NOX TELEMETRY HOLD: training.json locked; wrote training_safe70.json",
                  flush=True)
            return
        except PermissionError:
            # Never reuse a fixed filename when multiple local readers hold
            # Windows handles open without delete sharing. Preserve the real
            # receipt under a new immutable name.
            folder=path.parent/"safe70_receipts"
            folder.mkdir(exist_ok=True)
            unique=folder/("training_%d_%d.json"%(os.getpid(),time.time_ns()))
            os.replace(part,unique)
            print("NOX TELEMETRY HOLD: fixed JSON locked; saved",unique,flush=True)
            return
    finally:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass

def temperature():
    with urlopen(SENSOR,timeout=4) as r: data=json.loads(r.read(3_000_000))
    values=[]
    def visit(node,inside=False,depth=0):
        if depth>40 or not isinstance(node,dict):return
        name=str(node.get("Text","")).strip()
        if re.search(r"RX\s*6650M",name,re.I):inside=True
        elif re.search(r"^(AMD Radeon|NVIDIA|GeForce)",name,re.I):inside=False
        if inside and name=="GPU Hot Spot":
            m=re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*°\s*C",str(node.get("Value","")))
            if m:
                n=float(m.group(1).replace(",","."))
                if 0<n<110:values.append(n)
        for ch in node.get("Children") or []:visit(ch,inside,depth+1)
    visit(data)
    if not values:raise RuntimeError("RX6650M Hot Spot missing/zero")
    return max(values)

def battery():
    class P(ctypes.Structure):
        _fields_=[("AC",ctypes.c_byte),("Flag",ctypes.c_byte),
                  ("Pct",ctypes.c_byte),("Sys",ctypes.c_byte),
                  ("Life",ctypes.c_uint),("Full",ctypes.c_uint)]
    p=P()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p)):
        raise RuntimeError("battery status inaccessible")
    if p.AC not in (0,1) or not 0<=p.Pct<=100:raise RuntimeError("battery state unknown")
    return p.AC==1,int(p.Pct)

def latest_checkpoint(run_dirs):
    matches=[]
    for base in run_dirs:
        if not base.is_dir():continue
        for cp in base.glob("step-*"):
            if cp.is_symlink() or not cp.is_dir():continue
            m=re.fullmatch(r"step-(\d+)",cp.name)
            if not m:continue
            weight=cp/"adapter_model.safetensors"
            cfg=cp/"adapter_config.json"
            if not (weight.is_file() and weight.stat().st_size>1000 and cfg.is_file()):continue
            try:
                c=json.loads(cfg.read_text(encoding="utf-8"))
                name=str(c.get("base_model_name_or_path",""))
            except (OSError,ValueError):continue
            if not re.search(r"(?:qwen2\.5[-/])?0\.5b|qwen2\.5-0\.5b",name,re.I):
                continue
            matches.append((int(m.group(1)),weight.stat().st_mtime,cp))
    if not matches:raise RuntimeError("No compatible saved 0.5B adapter: fresh retraining forbidden")
    step,_,cp=max(matches,key=lambda z:(z[0],z[1]))
    return step,cp

def inputs():
    home=Path.home()
    roots=[ROOT/"brain"/"intelligence"/"adapters",
           home/"NOX_EXPRESS_AI"/"NOX_TRAINING"/"adapters",
           Path(r"C:\NOX_HELION\APP\NOX_TRAINING\adapters")]
    runs=[]
    for root in roots:
        if root.is_dir():
            runs.extend(p for pat in ("SAFE65_*","GPU_*","NOX_GPU_*","NOX_RESUME_*")
                        for p in root.glob(pat) if p.is_dir() and not p.is_symlink())
    step,cp=latest_checkpoint(runs)
    b=[Path(r"C:\NOX_HELION\APP\NOX_TRAINING"),home/"NOX_EXPRESS_AI"/"NOX_TRAINING"]
    model=next((p for base in b for p in (base/"models"/"Qwen2.5-0.5B-Instruct",)
                if p.is_dir()),None)
    dataset=next((p for base in b for p in (base/"datasets"/"knowledge_candidates.jsonl",)
                  if p.is_file()),None)
    if os.environ.get("NOX_USE_TEACHER_DISTILL_V1")=="1":
        # Explicitly selected local distilled dataset. Never silently replace
        # the owner's existing approved knowledge_candidates.jsonl.
        teacher_dir=ROOT/"brain"/"intelligence"/"distillation"
        candidate=teacher_dir/"teacher_candidates.jsonl"
        manifest=teacher_dir/"teacher_candidates.manifest.json"
        if not candidate.is_file() or not manifest.is_file() or candidate.is_symlink():
            raise RuntimeError("DISTILL_DATASET_NOT_READY")
        from hashlib import sha256
        meta=json.loads(manifest.read_text(encoding="utf-8"))
        h=sha256(candidate.read_bytes()).hexdigest()
        if meta.get("sha256")!=h or meta.get("status")!="DATASET_CANDIDATE_NOT_TRAINED":
            raise RuntimeError("DISTILL_DATASET_HASH_OR_STATUS_MISMATCH")
        if meta.get("student_base")!="Qwen2.5-0.5B-Instruct" or meta.get("examples",0)<8:
            raise RuntimeError("DISTILL_STUDENT_INCOMPATIBLE_OR_TOO_FEW_EXAMPLES")
        dataset=candidate
    if os.environ.get("NOX_USE_MULTI_TEACHER_V2")=="1":
        # Explicitly opted into a real multi-teacher curriculum with separate
        # untrained held-out set. Never silently mix S03 or personal chat data.
        from hashlib import sha256
        base=ROOT/"brain"/"intelligence"/"distillation"
        selected=base/"multi_teacher_student_v1.jsonl"
        held=base/"multi_teacher_holdout_v1.jsonl"
        report=base/"multi_teacher_student_v1.manifest.json"
        if not all(p.is_file() and not p.is_symlink() for p in (selected,held,report)):
            raise RuntimeError("MULTI_TEACHER_STUDENT_DATASET_NOT_READY")
        info=json.loads(report.read_text(encoding="utf-8"))
        if (info.get("schema")!="NOX_PRIME_STUDENT_TRAIN_V1"
            or info.get("student_base")!="Qwen2.5-0.5B-Instruct"
            or info.get("status")!="TRAINING_READY_RESEARCH_STUDENT_NOT_ACCEPTED"):
            raise RuntimeError("MULTI_TEACHER_STUDENT_BASE_OR_STATE_HOLD")
        if (sha256(selected.read_bytes()).hexdigest()!=info.get("train_sha256")
            or sha256(held.read_bytes()).hexdigest()!=info.get("heldout_sha256")
            or info.get("train_examples",0)<8 or info.get("heldout_examples",0)<2):
            raise RuntimeError("MULTI_TEACHER_DATASET_INTEGRITY_OR_SPLIT_HOLD")
        dataset=selected
    if not model or not dataset:raise RuntimeError("Local base model or approved NOX dataset missing")
    return step,cp,model,dataset

def worker(a):
    import torch,torch_directml
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    device=torch_directml.device()
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
    if tokenizer.pad_token is None:tokenizer.pad_token=tokenizer.eos_token
    base=AutoModelForCausalLM.from_pretrained(a.model,torch_dtype=torch.float32,local_files_only=True)
    base.config.use_cache=False
    model=PeftModel.from_pretrained(base,a.checkpoint,is_trainable=True)
    model.to(device);model.train()
    trainable=[p for p in model.parameters() if p.requires_grad]
    if not trainable:raise RuntimeError("No trainable LoRA parameters")
    opt=torch.optim.AdamW(trainable,lr=1e-5,foreach=False)
    data=[]
    if os.environ.get("NOX_USE_TEACHER_DISTILL_V1")=="1":
        # Child inherits opt-in mode; re-check immutable teacher bytes.
        from hashlib import sha256
        manifest=ROOT/"brain"/"intelligence"/"distillation"/"teacher_candidates.manifest.json"
        m=json.loads(manifest.read_text(encoding="utf-8"))
        if sha256(a.dataset.read_bytes()).hexdigest()!=m.get("sha256"):
            raise RuntimeError("DISTILL_DATASET_CHANGED_AFTER_PREFLIGHT")
    if os.environ.get("NOX_USE_MULTI_TEACHER_V2")=="1":
        from hashlib import sha256
        check=ROOT/"brain"/"intelligence"/"distillation"/"multi_teacher_student_v1.manifest.json"
        proof=json.loads(check.read_text(encoding="utf-8"))
        if sha256(a.dataset.read_bytes()).hexdigest()!=proof.get("train_sha256"):
            raise RuntimeError("MULTI_TEACHER_TRAIN_DATASET_CHANGED")
    for line in a.dataset.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():continue
        item=json.loads(line)
        if not isinstance(item,dict):continue
        msgs=item.get("messages")
        if isinstance(msgs,list):
            text="\n".join(str(x.get("content","")) for x in msgs if isinstance(x,dict))
        else:
            text=(item.get("text") or item.get("content") or
                  "\n".join(str(item.get(k,"")) for k in ("prompt","response","instruction","output")))
        if isinstance(text,str) and len(text.strip())>20:data.append(text)
    if not data:raise RuntimeError("Dataset has no supported approved text rows")
    for n in range(1,a.steps+1):
        tokens=tokenizer(data[(a.start+n-1)%len(data)],max_length=128,
                         truncation=True,return_tensors="pt")
        ids=tokens["input_ids"].to(device)
        if ids.size(1)<3:raise RuntimeError("Selected training sample too short")
        opt.zero_grad(set_to_none=True)
        loss=model(input_ids=ids,labels=ids).loss
        if not bool(torch.isfinite(loss).item()):raise RuntimeError("Nonfinite loss")
        loss.backward();opt.step()
        step=a.start+n
        print(json.dumps({"step":step,"loss":round(float(loss.detach().cpu().item()),6),
                          "device":"DirectML","pid":os.getpid(),
                          "data_source":"LOCAL_MULTI_TEACHER_V2" if os.environ.get("NOX_USE_MULTI_TEACHER_V2")=="1"
                                      else "LOCAL_TEACHER_DISTILL" if os.environ.get("NOX_USE_TEACHER_DISTILL_V1")=="1"
                                      else "EXISTING_APPROVED_KNOWLEDGE"}),flush=True)
        if n%5==0 or n==a.steps:
            target=a.out/("step-%06d"%step)
            pending=a.out/(".pending-%06d"%step)
            if target.exists() or pending.exists():raise RuntimeError("Checkpoint collision")
            # DirectML uses OpaqueTensorImpl storage; PEFT's default
            # save_pretrained -> safetensors cannot access that GPU storage.
            # Explicitly copy *only LoRA adapter tensors* to CPU before writing.
            # Do not change module/optimizer device in the middle of training.
            from peft import get_peft_model_state_dict
            from safetensors.torch import save_file,load_file
            pending.mkdir(parents=True)
            peft_state=get_peft_model_state_dict(model,adapter_name="default")
            cpu_state={k:v.detach().to("cpu").contiguous()
                       for k,v in peft_state.items()}
            if not cpu_state or not all(v.device.type=="cpu" for v in cpu_state.values()):
                raise RuntimeError("Adapter CPU snapshot failed")
            model.peft_config["default"].save_pretrained(pending)
            weight_file=pending/"adapter_model.safetensors"
            save_file(cpu_state,str(weight_file),metadata={"format":"pt"})
            loaded=load_file(str(weight_file),device="cpu")
            if set(loaded)!=set(cpu_state) or any(
                loaded[k].shape!=cpu_state[k].shape for k in cpu_state
            ):
                raise RuntimeError("Adapter checkpoint roundtrip mismatch")
            del cpu_state,peft_state,loaded
            pending.rename(target)
            print(json.dumps({"checkpoint":str(target),"step":step}),flush=True)

def stop_tree(pid):
    subprocess.run(["taskkill.exe","/PID",str(pid),"/T","/F"],
                   capture_output=True,timeout=15)

def single_cycle():
    step,checkpoint,model,dataset=inputs()
    if step>=TARGET_TOTAL_STEPS:
        return "GOAL"
    chunk=min(20,TARGET_TOTAL_STEPS-step)
    if shutil.disk_usage(ROOT).free<60_000_000_000:
        raise RuntimeError("60GB free disk reserve required")
    hot=temperature();ac,charge=battery()
    if hot>=LIMIT or (not ac and charge<=25):
        raise RuntimeError("Unsafe pre-start temperature or battery")
    check=("Get-CimInstance Win32_Process | Where-Object {"
           "$_.Name -match '^python' -and "
           "$_.CommandLine -match 'train_directml_lora[.]py|nox_gpu_safe65_v2[.]py.+--worker'"
           "} | Select-Object -ExpandProperty ProcessId")
    p=subprocess.run(["powershell.exe","-NoProfile","-Command",check],
                     capture_output=True,text=True,timeout=15)
    if any(x.strip().isdigit() for x in p.stdout.splitlines()):
        raise RuntimeError("Another GPU trainer exists; refusing concurrent run")
    outdir=ROOT/"brain"/"intelligence"/"adapters"/("NOX_RESUME_"+datetime.now().strftime("%Y%m%d_%H%M%S"))
    outdir.mkdir(parents=True,exist_ok=False)
    (outdir/"SOURCE_CHECKPOINT.txt").write_text(str(checkpoint),encoding="utf-8")
    log=outdir/"training.log";errs=outdir/"errors.log"
    tele=ROOT/"brain"/"telemetry"/"training.json"
    args=[sys.executable,str(Path(__file__).resolve()),"--worker",
          "--model",str(model),"--dataset",str(dataset),"--checkpoint",str(checkpoint),
          "--start",str(step),"--steps",str(chunk),"--out",str(outdir)]
    env=dict(os.environ,OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",
             HF_HOME=str(ROOT/"brain"/"intelligence"/"hf_cache"),
             TMP=str(ROOT/"brain"/"skills"/"tmp"),
             TEMP=str(ROOT/"brain"/"skills"/"tmp"))
    for k in ("HF_HOME","TMP"):Path(env[k]).mkdir(parents=True,exist_ok=True)
    print("NOX DATASET SOURCE:",dataset,"mode:",
          "MULTI_TEACHER_V2" if os.environ.get("NOX_USE_MULTI_TEACHER_V2")=="1"
          else os.environ.get("NOX_USE_TEACHER_DISTILL_V1","existing"),
          flush=True)
    print("NOX AMD SAFE70 | LoRA weight continuation",checkpoint,
          "| HotSpot",hot,"C | battery",charge,"%",flush=True)
    with log.open("w",encoding="utf-8") as o,errs.open("w",encoding="utf-8") as e:
        child=subprocess.Popen(args,stdout=o,stderr=e,env=env,
              cwd=str(outdir),creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0))
    last_step=step;last_loss=None;reason=None
    thermal_guard=ThermalGuard()
    try:
        while child.poll() is None:
            try:
                hot=temperature();ac,charge=battery()
                thermal_reason,hot_streak=thermal_guard.sample(hot)
                if thermal_reason=="SENSOR_INVALID":
                    reason="SENSOR/BATTERY_LOST INVALID_HOTSPOT"
                elif thermal_reason:
                    reason=thermal_reason
                elif not ac and charge<=20:
                    reason="BATTERY<=20%"
                elif shutil.disk_usage(ROOT).free<60_000_000_000:
                    reason="DISK_RESERVE"
                if not reason and hot_streak:
                    print("NOX SAFE70 WARN: Hot Spot",hot,"C | consecutive",
                          hot_streak,"/3 | stop at 3, immediate at 75C",flush=True)
            except Exception as ex:
                hot=None;reason="SENSOR/BATTERY_LOST "+str(ex)
            try:
                for line in log.read_text(encoding="utf-8",errors="replace").splitlines()[-50:]:
                    try:
                        x=json.loads(line)
                        if type(x.get("step")) is int:
                            last_step=max(last_step,x["step"])
                            if isinstance(x.get("loss"),(int,float)):last_loss=x["loss"]
                    except (ValueError,AttributeError):pass
            except OSError:pass
            if reason:
                print("NOX HARD STOP",reason,flush=True)
                stop_tree(child.pid)
            receipt(tele,{"status":"SAFETY_HOLD" if reason else "running",
                "actual_steps":last_step,"requested_steps":TARGET_TOTAL_STEPS,
                "loss_metrics":{"loss":last_loss} if last_loss is not None else {},
                "process_id":child.pid,"gpu_temperature_c":hot,"gpu_hotspot_c":hot,
                "battery_percent":charge,"timestamp":datetime.now(timezone.utc).isoformat(),
                "thermal_hot_streak":thermal_guard.streak,
                "thermal_soft_limit_c":70,"thermal_hard_limit_c":75,
                "output_directory":str(outdir)})
            if reason:break
            print("NOX GPU",hot,"C | step",last_step,"| battery",charge,"% | pid",child.pid,flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        reason="MANUAL_STOP";stop_tree(child.pid)
    except BaseException:
        # Unexpected dashboard/file IO must never orphan a live DirectML worker.
        # Only the supervision process may own or restart the GPU child.
        reason="CONTROLLER_ERROR"
        stop_tree(child.pid)
        raise
    finally:
        try:
            child.wait(timeout=25)
        except subprocess.TimeoutExpired:
            stop_tree(child.pid)
            child.wait(timeout=25)
        receipt(tele,{"status":"SAFETY_HOLD" if reason else
                     ("DONE" if child.returncode==0 else "TRAINING_FAILED"),
                     "actual_steps":last_step,"requested_steps":TARGET_TOTAL_STEPS,
                     "process_id":child.pid,"timestamp":datetime.now(timezone.utc).isoformat(),
                     "output_directory":str(outdir)})
    if reason:
        print("NOX SAFE70 stop:",reason,"| last SAVED checkpoint preserved.",flush=True)
    elif child.returncode!=0:
        print("NOX train error:",errs.read_text(encoding="utf-8",errors="replace")[-2500:],flush=True)
    else:
        saved=outdir/("step-%06d"%(step+chunk))
        if not (saved/"adapter_config.json").is_file() or not (saved/"adapter_model.safetensors").is_file():
            print("NOX CHECKPOINT MISSING; no automatic restart",flush=True)
            return "TRAINING_FAILED"
        print("NOX",chunk,"additional LoRA steps saved; evaluation still required.",flush=True)
    print("NOX OUTPUT:",outdir,flush=True)
    if reason:
        # The original PID exiting is not proof a descendant GPU worker stopped.
        # Fail closed on a failed taskkill instead of treating receipt as proof.
        if child.poll() is None:
            raise RuntimeError("GPU_WORKER_STILL_ALIVE: no restart")
        return reason
    return "COMPLETE" if child.returncode==0 else "TRAINING_FAILED"

def supervise():
    """Continue from the latest complete adapter ONLY after a verified cool-down.

    No blind retries of a failed model; bounded cycles/restarts. Hard stops can
    lose in-flight gradients but never overwrite already saved adapters.
    """
    cycles=0
    thermal_restarts=0
    while cycles<MAX_CYCLES:
        outcome=single_cycle()
        cycles+=1
        if outcome=="GOAL":
            print("NOX TARGET ACHIEVED:",TARGET_TOTAL_STEPS,"saved steps",flush=True)
            return
        if outcome=="COMPLETE":
            print("NOX CYCLE",cycles,"saved; next cycle uses latest checkpoint.",flush=True)
            if cycles>=MAX_CYCLES:
                print("NOX CYCLE CAP: target unconfirmed; stopping safely.",flush=True)
                raise RuntimeError("CYCLE_CAP_BEFORE_TARGET")
            # Sample sensor before next cycle. A finished cycle is not a cooling
            # event, but no new cycle may start while hot or on low battery.
            try:
                hot=temperature()
                ac,charge=battery()
            except Exception as ex:
                print("NOX SENSOR HOLD:",ex,flush=True)
                raise RuntimeError("SENSOR_HOLD") from ex
            if hot<LIMIT and (ac or charge>30):
                continue
            outcome="HOTSPOT_COOLDOWN" if hot>=LIMIT else "BATTERY_HOLD"
        if isinstance(outcome,str) and outcome.startswith("SENSOR/BATTERY_LOST"):
            # The DirectML worker was already hard-stopped by single_cycle().
            # Never train with an unknown Hot Spot. The outer worm will watch
            # LibreHardwareMonitor and require stable, repeated valid readings.
            print("NOX SENSOR RECOVERY REQUIRED; GPU worker stopped; checkpoint intact.",
                  flush=True)
            raise RuntimeError("SENSOR_RECOVERY_REQUIRED")
        if outcome not in ("HOTSPOT>=70C","HOTSPOT>=75C","HOTSPOT_COOLDOWN"):
            print("NOX stopped, NO automatic restart:",outcome,flush=True)
            raise RuntimeError("STOP_BEFORE_TARGET: "+str(outcome))
        thermal_restarts+=1
        if thermal_restarts>MAX_THERMAL_RESTARTS:
            print("NOX thermal restart limit reached; checkpoint safe.",flush=True)
            raise RuntimeError("EXCESSIVE_THERMAL_STOPS")
        # Always cool at least 180 seconds after a confirmed or emergency thermal stop.
        print("NOX cooling for >=180s; next cycle requires Hot Spot <65C.",flush=True)
        time.sleep(COOL)
        while True:
            try:
                hot=temperature()
                ac,charge=battery()
            except Exception as ex:
                print("NOX sensor lost; fail closed:",ex,flush=True)
                raise RuntimeError("SENSOR_LOST_DURING_COOLDOWN") from ex
            if hot<RESUME_BELOW and (ac or charge>30):
                print("NOX cooled to",hot,"C; restart from latest saved adapter.",flush=True)
                break
            print("NOX HOLD HotSpot",hot,"C; battery",charge,"%; no GPU work.",flush=True)
            time.sleep(30)
    raise RuntimeError("CYCLE_CAP_BEFORE_TARGET")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--worker",action="store_true")
    ap.add_argument("--model",type=Path)
    ap.add_argument("--dataset",type=Path)
    ap.add_argument("--checkpoint",type=Path)
    ap.add_argument("--start",type=int)
    ap.add_argument("--steps",type=int)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.worker:worker(args)
    else:supervise()
