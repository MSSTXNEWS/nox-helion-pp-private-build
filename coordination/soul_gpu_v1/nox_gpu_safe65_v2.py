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

ROOT=Path(r"C:\NOX_HELION\NOX_NEW")
SENSOR="http://127.0.0.1:8085/data.json"
LIMIT=70
COOL=180

def receipt(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    part=path.with_suffix(".tmp")
    part.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(part,path)

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
                          "device":"DirectML","pid":os.getpid()}),flush=True)
        if n%5==0 or n==a.steps:
            target=a.out/("step-%06d"%step)
            pending=a.out/(".pending-%06d"%step)
            if target.exists() or pending.exists():raise RuntimeError("Checkpoint collision")
            model.save_pretrained(pending,safe_serialization=True)
            if not (pending/"adapter_model.safetensors").is_file():
                raise RuntimeError("Checkpoint write not verified")
            pending.rename(target)
            print(json.dumps({"checkpoint":str(target),"step":step}),flush=True)

def stop_tree(pid):
    subprocess.run(["taskkill.exe","/PID",str(pid),"/T","/F"],
                   capture_output=True,timeout=15)

def supervise():
    step,checkpoint,model,dataset=inputs()
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
          "--start",str(step),"--steps","20","--out",str(outdir)]
    env=dict(os.environ,OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",
             HF_HOME=str(ROOT/"brain"/"intelligence"/"hf_cache"),
             TMP=str(ROOT/"brain"/"skills"/"tmp"),
             TEMP=str(ROOT/"brain"/"skills"/"tmp"))
    for k in ("HF_HOME","TMP"):Path(env[k]).mkdir(parents=True,exist_ok=True)
    print("NOX AMD SAFE70 | LoRA weight continuation",checkpoint,
          "| HotSpot",hot,"C | battery",charge,"%",flush=True)
    with log.open("w",encoding="utf-8") as o,errs.open("w",encoding="utf-8") as e:
        child=subprocess.Popen(args,stdout=o,stderr=e,env=env,
              cwd=str(outdir),creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0))
    last_step=step;last_loss=None;reason=None
    try:
        while child.poll() is None:
            try:
                hot=temperature();ac,charge=battery()
                if hot>=LIMIT:reason="HOTSPOT>=70C"
                elif not ac and charge<=20:reason="BATTERY<=20%"
                elif shutil.disk_usage(ROOT).free<60_000_000_000:reason="DISK_RESERVE"
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
                "actual_steps":last_step,"requested_steps":step+20,
                "loss_metrics":{"loss":last_loss} if last_loss is not None else {},
                "process_id":child.pid,"gpu_temperature_c":hot,"gpu_hotspot_c":hot,
                "battery_percent":charge,"timestamp":datetime.now(timezone.utc).isoformat(),
                "output_directory":str(outdir)})
            if reason:break
            print("NOX GPU",hot,"C | step",last_step,"| battery",charge,"% | pid",child.pid,flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        reason="MANUAL_STOP";stop_tree(child.pid)
    finally:
        child.wait(timeout=25)
        receipt(tele,{"status":"SAFETY_HOLD" if reason else
                     ("DONE" if child.returncode==0 else "TRAINING_FAILED"),
                     "actual_steps":last_step,"requested_steps":step+20,
                     "process_id":child.pid,"timestamp":datetime.now(timezone.utc).isoformat(),
                     "output_directory":str(outdir)})
    if reason:
        print("NOX 180-second cooldown. NO AUTO-RESTART; last saved checkpoint intact.",flush=True)
        time.sleep(COOL)
    elif child.returncode!=0:
        print("NOX train error:",errs.read_text(encoding="utf-8",errors="replace")[-2500:],flush=True)
    else:print("NOX 20 added LoRA steps saved; holdout approval still required.",flush=True)
    print("NOX OUTPUT:",outdir,flush=True)

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
