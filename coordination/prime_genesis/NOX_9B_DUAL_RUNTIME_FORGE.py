#!/usr/bin/env python3
"""NOX PRIME 9B experimental supervised LoRA: CPU full-model loss, DirectML LoRA gradients.

Architecture: Qwen3.5-9B BF16 base is immutable CPU; only down_proj LoRA
parameters receive gradients on RX6650M DirectML in a separate Python runtime.
Stages S8..S1 (4 text layers each). No success without independent loss reduction,
new adapter safetensors hash and verified GPU step receipt. Experimental only.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from datetime import datetime, timezone

PRIME = Path(r'C:\NOX_HELION\NOX_NEW\brain\prime')
BRAIN = PRIME.parent
MODEL = PRIME / 'models' / 'NOX_PRIME_9B_INHERITED'
EMBRYO = BRAIN / 'NOX_EMBRYO_GENESIS_V1'
OUT = PRIME / 'forge9b'
SENSOR = 'http://127.0.0.1:8085/data.json'


def utc(): return datetime.now(timezone.utc).isoformat()

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def atomic_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=str(path.parent),suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def read_sensor():
    from urllib.request import urlopen,Request
    with urlopen(Request(SENSOR,headers={'Accept':'application/json'}), timeout=3) as resp:
        d=json.load(resp)
    readings=[]
    def rec(node,parent=''):
        if isinstance(node,list):
            for x in node:rec(x,parent)
        elif isinstance(node,dict):
            label=' '.join(str(node.get(k,'')) for k in ('Text','Name','HardwareName','Identifier'))
            path=parent+' '+label
            if re.search(r'RX\s*6650\s*M',path,re.I) and re.search(r'Hot\s*Spot|Hotspot|Junction',label,re.I):
                m=re.search(r'[-+]?\d+(?:[.,]\d+)?',str(node.get('Value',node.get('value',''))))
                if not m:raise ValueError('GPU Hot Spot missing value')
                readings.append(float(m.group().replace(',','.')))
            for x in node.values():
                if isinstance(x,(list,dict)):rec(x,path)
    rec(d)
    if not readings or any(not math.isfinite(t) or t<=0 or t>=120 for t in readings):
        raise RuntimeError('SAFE70_HOLD: RX6650M Hot Spot missing/invalid')
    if max(readings)-min(readings)>3:raise RuntimeError('SAFE70_HOLD: ambiguous readings')
    return max(readings)

def write_progress(hotspot=None, runtime='RUNNING'):
    """Display only receipt-backed experimental LoRA steps; never mark 9B merged."""
    from html import escape
    cells=[];count=0
    for stage in range(1,9):
        rfile=OUT/('S%d.receipt.json'%stage)
        weights=OUT/('S%d.safetensors'%stage)
        ok=False;loss=''
        if rfile.is_file() and weights.is_file():
            try:
                r=json.loads(rfile.read_text(encoding='utf-8'))
                ok=(r['status']=='EXPERIMENTAL_ADAPTER_TRAINED'
                    and r['training_loss_after']<r['training_loss_before']
                    and r['optimizer_steps']>=1 and sha(weights)==r['sha256'])
                if ok:loss='loss %.4f → %.4f'%(r['training_loss_before'],r['training_loss_after'])
            except Exception:pass
        count+=int(ok)
        cells.append('<div class="cell %s"><b>S%d</b><small>Layers %d–%d</small><span>%s</span><small>%s</small></div>'%(
            'good' if ok else 'pending',stage,(stage-1)*4+1,stage*4,
            'GPU LoRA experimental' if ok else 'Not trained',loss))
    temp='—' if hotspot is None else ('%.1f°C'%hotspot)
    html="""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta http-equiv="refresh" content="9"><meta name="viewport" content="width=device-width, initial-scale=1"><title>NOX HELION · PRIME FORGE 9B</title><style>body{background:#070a0e;color:#f6e7c8;font-family:Segoe UI,Arial,sans-serif;padding:5vw;max-width:1300px;margin:auto}h1{letter-spacing:.14em;font-size:30px}h2{font-size:60px;margin:10px 0}.sub{color:#aaa}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin-top:35px}.cell{background:#121821;border:1px solid #66543d;border-radius:14px;padding:25px;display:flex;flex-direction:column;gap:15px}.cell b{font-size:26px}.cell span{color:#c3a77f}.cell small{color:#89919f}.good{border-color:#4db09b}.warn{border-top:2px solid #715b31;margin-top:35px;padding-top:20px}</style></head><body><div class="sub">NOX HELION / PRIME / GPU FORGE</div><h1>SEGMENTED 9B LORA</h1><h2>{count}/8</h2><div class="sub">Completed experimental stages with verified DirectML updates (not 9B full finetune)</div><p>Hot Spot: {temp}　 ·  State: {runtime}　 ·  Base 19.3GB: IMMUTABLE</p><main>{cells}</main><div class="warn">⚠ No full-model skill transfer, no standalone merged 9B accepted yet. CPU model loss / DirectML adapter gradient. User S03 and base Qwen weights preserved.</div></body></html>""".replace('{count}',str(count)).replace('{temp}',escape(temp)).replace('{runtime}',escape(runtime)).replace('{cells}',''.join(cells))
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/'NOX_9B_GPU_PROGRESS.html'
    fd,tmp=tempfile.mkstemp(dir=str(OUT),suffix='.html.tmp')
    with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(html)
    os.replace(tmp,path)
    return count


def model_manifest():
    m=json.loads((PRIME/'NOX_PRIME_9B_MANIFEST.json').read_text(encoding='utf-8'))
    if m.get('status')!='INHERITED_UNTRAINED' or m.get('source_repository')!='Qwen/Qwen3.5-9B':
        raise RuntimeError('NOX source model manifest invalid')
    if Path(m.get('model_root','')).resolve()!=MODEL.resolve():raise RuntimeError('NOX model location mismatch')
    if m.get('training_steps_on_9b',0)!=0:raise RuntimeError('Base weight lineage changed: HOLD')
    total=0
    for o in m.get('shards',[]):
        p=MODEL/o['file']
        if not p.is_file() or p.stat().st_size!=o['bytes']:raise RuntimeError('Source shard missing: '+str(p))
        total+=o['bytes']
    if total<8*1024**3:raise RuntimeError('Insufficient base weight bytes')
    config=json.loads((MODEL/'config.json').read_text(encoding='utf-8'))
    if config.get('model_type')!='qwen3_5' or config.get('text_config',{}).get('num_hidden_layers')!=32:
        raise RuntimeError('Qwen3.5 text architecture mismatch')
    return m

def examples():
    file=EMBRYO/'data'/'teacher_experiment.jsonl'
    if not file.exists():file=EMBRYO/'data'/'approved_teacher.jsonl'
    if not file.is_file():raise RuntimeError('NOX experimental training examples missing')
    data=[]
    for raw in file.read_text(encoding='utf-8-sig').splitlines():
        if not raw.strip():continue
        row=json.loads(raw)
        if row.get('teacher')=='qwen3.5:9b' and row.get('may_train') is True:
            prompt=row.get('prompt','');ans=row.get('answer','')
            if len(prompt)>=15 and len(ans)>=20:data.append((prompt,ans))
    if len(data)<4:raise RuntimeError('NOX HOLD: fewer than four teacher examples')
    return file,data

def check_host():
    import psutil
    battery=psutil.sensors_battery()
    if battery is not None and battery.percent < 25 and not battery.power_plugged:
        raise RuntimeError('BATTERY_HOLD: charge below 25%')
    mem=psutil.virtual_memory()
    if mem.total < 32*1024**3 or mem.available < 25*1024**3:
        raise RuntimeError('RAM_HOLD: CPU full 9B backbone requires >=32GiB total and >=25GiB available RAM; current available %.1f GiB'%(mem.available/1024**3))
    m=model_manifest();f,d=examples();
    for _ in range(3):
        t=read_sensor()
        if t>=70:raise RuntimeError('SAFE70_HOLD: preflight %.1f C'%t)
        time.sleep(1)
    return m,f,d

def gpu_probe():
    import torch,torch_directml
    device=torch_directml.device()
    a=torch.tensor([[2.0,1.0]],device=device,requires_grad=True)
    b=torch.tensor([[3.0],[4.0]],device=device,requires_grad=True)
    x=(a@b).sum();x.backward()
    if a.grad is None or b.grad is None or abs(float(a.grad.detach().cpu()[0,0])-3)>1e-3:
        raise RuntimeError('DirectML gradient verification failed')
    print('DIRECTML GRADIENT PASS',device,torch.__version__,flush=True)

def gpu_step(root, stage, data_path, out_path):
    import torch,torch_directml,numpy as np
    from safetensors.torch import save_file,load_file
    gpu_probe();dev=torch_directml.device();rank=4;alpha=8.0
    packet=np.load(data_path,allow_pickle=False)
    original=Path(root)/('S%d.safetensors'%stage)
    state=load_file(str(original)) if original.exists() else {}
    result={}; trained=[]
    for layer in range((stage-1)*4,stage*4):
        key=str(layer)
        if ('x'+key) not in packet.files or ('g'+key) not in packet.files:raise RuntimeError('Missing gradients for layer '+key)
        X=torch.from_numpy(packet['x'+key].astype('float32')).to(dev)
        G=torch.from_numpy(packet['g'+key].astype('float32')).to(dev)
        a_key='layer'+key+'.A';b_key='layer'+key+'.B'
        d=X.size(1);o=G.size(1)
        if 'a'+key not in packet.files or 'b'+key not in packet.files:
            raise RuntimeError('CPU forward weights missing for DML gradient consistency')
        A=torch.nn.Parameter(torch.from_numpy(packet['a'+key].astype('float32')).to(dev))
        B=torch.nn.Parameter(torch.from_numpy(packet['b'+key].astype('float32')).to(dev))
        if A.shape != (rank,d) or B.shape != (o,rank):
            raise RuntimeError('LoRA stage shapes mismatch: '+key)
        opt=torch.optim.AdamW([A,B],lr=0.03,weight_decay=0.0)
        opt.zero_grad(set_to_none=True)
        delta=(X@A.T)@B.T*(alpha/rank)
        surrogate=(delta*G).sum()
        if not bool(torch.isfinite(surrogate.detach()).cpu().item()):raise RuntimeError('GPU nonfinite objective')
        surrogate.backward()
        if B.grad is None or not bool(torch.isfinite(B.grad.detach()).all().cpu().item()):raise RuntimeError('GPU gradient invalid')
        grad_norm=float(B.grad.detach().float().cpu().norm())
        if grad_norm<=0:raise RuntimeError('GPU gradient zero: no learning')
        opt.step()
        result[a_key]=A.detach().cpu().contiguous().float();result[b_key]=B.detach().cpu().contiguous().float()
        trained.append({'layer':layer,'gradient_norm':grad_norm,'in_shape':list(X.shape),'out_shape':list(G.shape)})
    # Stage's weights are installed only after CPU confirms loss decrease.
    dest=Path(out_path);dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_name(dest.name+'.partial');save_file(result,str(tmp));os.replace(tmp,dest)
    atomic_json(dest.with_suffix('.gpu.json'),{'status':'DML_OPTIMIZER_STEP','gpu_device':str(dev),'stage':stage,'trained_layers':trained,'sha256':sha(dest),'timestamp':utc()})
    print('GPU_LORA_STEP_PASS',json.dumps({'stage':stage,'layers':trained,'sha256':sha(dest)},ensure_ascii=False),flush=True)

class LoRAWrapped:
    """Injected nn.Module definition must be initialized after torch import."""
    @staticmethod
    def make(torch,base,layer_idx,A=None,B=None):
        class Wrapper(torch.nn.Module):
            def __init__(self):
                super().__init__();self.base=base;self.layer=layer_idx
                self.A=A.cpu().float() if A is not None else torch.randn(4,base.in_features).float()*0.02
                self.B=B.cpu().float() if B is not None else torch.zeros(base.out_features,4).float()
                self.x=None;self.tap=None
            def forward(self,x):
                # Fixed base CPU linear, training gradient tap. CPU LoRA delta is the
                # same function as DirectML update, used for exact chain-rule gradient.
                z=torch.nn.functional.linear(torch.nn.functional.linear(x.float(),self.A),self.B)*2.0
                y=self.base(x)+z.to(x.dtype)
                tap=torch.zeros_like(y,requires_grad=True)
                self.x=x.detach().float().cpu();self.tap=tap
                return y+tap
        return Wrapper()

def make_tokens(tokenizer,prompt,answer,limit=72):
    import torch
    p=tokenizer.encode(prompt,add_special_tokens=False)[:24]
    a=tokenizer.encode(answer,add_special_tokens=False)[:max(8,limit-len(p))]
    tokens=p+a
    if len(p)<2 or len(a)<2:raise RuntimeError('Empty/invalid train text tokens')
    labels=[-100]*len(p)+a
    return torch.tensor([tokens]),torch.tensor([labels])

def forward_loss(model,input_ids,labels):
    import torch
    out=model(input_ids=input_ids,attention_mask=torch.ones_like(input_ids),use_cache=False,return_dict=True)
    logits=out.logits
    loss=torch.nn.functional.cross_entropy(logits[:, :-1,:].float().contiguous().view(-1,logits.shape[-1]),labels[:,1:].contiguous().view(-1),ignore_index=-100)
    return loss

def train_cpu(gpu_python,script,limit_stages):
    import torch,psutil
    from safetensors.torch import load_file
    m,exfile,rows=check_host()
    # Separate CPU environment with PyTorch >=2.6 for the Qwen3.5 reference code.
    from transformers import Qwen3_5ForConditionalGeneration,AutoTokenizer
    print('CPU_BF16_BACKBONE_LOADING: 19.3 GB no-copy model',flush=True)
    model=Qwen3_5ForConditionalGeneration.from_pretrained(str(MODEL),dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='eager',trust_remote_code=False)
    model.requires_grad_(False);model.eval()
    # Torch autograd is enabled for gradients propagated to the CPU taps.
    layers=model.model.language_model.layers
    if len(layers)!=32:raise RuntimeError('9B loaded model decoder layer count mismatch')
    tokenizer=AutoTokenizer.from_pretrained(str(MODEL),trust_remote_code=False)
    OUT.mkdir(parents=True,exist_ok=True)
    next_stages=list(range(8,0,-1))[:limit_stages]
    for stage in next_stages:
        status_path=OUT/('S%d.receipt.json'%stage)
        resumed=False
        saved=OUT/('S%d.safetensors'%stage)
        previous_state={}
        if status_path.exists():
            prev=json.loads(status_path.read_text(encoding='utf-8'))
            if prev.get('status')=='EXPERIMENTAL_ADAPTER_TRAINED' and saved.is_file() and sha(saved)==prev.get('sha256'):
                previous_state=load_file(str(saved))
                resumed=True
        wrappers={}
        for idx in range((stage-1)*4,stage*4):
            original=layers[idx].mlp.down_proj
            a=previous_state.get('layer%d.A'%idx) if resumed else None
            b=previous_state.get('layer%d.B'%idx) if resumed else None
            wrappers[idx]=LoRAWrapped.make(torch,original,idx,a,b)
            layers[idx].mlp.down_proj=wrappers[idx]
        if resumed:
            print('STAGE_REUSED_WITH_ADAPTER',stage,flush=True)
            continue
        prompt,answer=rows[(8-stage)%len(rows)]
        inp,lab=make_tokens(tokenizer,prompt,answer)
        print('STAGE_START',stage,'layers',list(wrappers),flush=True)
        # Gradients computed against the real complete 9B causal-language loss.
        model.zero_grad(set_to_none=True)
        loss=forward_loss(model,inp,lab)
        before=float(loss.detach().cpu())
        if not math.isfinite(before):raise RuntimeError('Nonfinite 9B objective at S%d'%stage)
        loss.backward()
        tensors={}
        for idx,wrap in wrappers.items():
            if wrap.tap is None or wrap.tap.grad is None:raise RuntimeError('Missing end-to-end 9B gradient for layer %d'%idx)
            tensors['x'+str(idx)]=wrap.x.detach().numpy().reshape(-1,wrap.x.shape[-1])
            tensors['g'+str(idx)]=wrap.tap.grad.detach().cpu().float().numpy().reshape(-1,wrap.tap.grad.shape[-1])
            tensors['a'+str(idx)]=wrap.A.detach().cpu().numpy()
            tensors['b'+str(idx)]=wrap.B.detach().cpu().numpy()
        packet=OUT/('S%d.data.npz'%stage);import numpy as np;np.savez_compressed(packet,**tensors)
        candidate=OUT/('S%d.candidate.safetensors'%stage)
        proc=subprocess.run([str(gpu_python),str(script),'--gpu-step','--stage',str(stage),'--packet',str(packet),'--output',str(candidate)],cwd=str(OUT),check=False)
        if proc.returncode:raise RuntimeError('DML GPU training step failed at stage %d'%stage)
        upd=load_file(str(candidate))
        # Bfloat16 output quantization can flatten tiny SGD steps. Use actual
        # CPU model loss for bounded line-search; no promotion without decrease.
        old={idx:(wrap.A.detach().clone(),wrap.B.detach().clone()) for idx,wrap in wrappers.items()}
        accepted=False;after=float('inf');factor=0.0
        for scale in (1.0,0.5,0.2,0.08,0.03):
            for idx,wrap in wrappers.items():
                oa,ob=old[idx]
                wrap.A=oa+(upd['layer%d.A'%idx].float()-oa)*scale
                wrap.B=ob+(upd['layer%d.B'%idx].float()-ob)*scale
            model.zero_grad(set_to_none=True)
            with torch.no_grad(): after=float(forward_loss(model,inp,lab).detach().cpu())
            if math.isfinite(after) and after < before-1e-5:
                accepted=True;factor=scale;break
        if not accepted:
            raise RuntimeError('NO_GAIN_HOLD at S%d: no loss decrease; previous model and accepted stages unchanged, baseline %.6f last %.6f'%(stage,before,after))
        # Persist precisely the adapters accepted by the full 9B CPU evaluation.
        import safetensors.torch
        accepted_state={}
        for idx,wrap in wrappers.items():
            accepted_state['layer%d.A'%idx]=wrap.A.float().contiguous()
            accepted_state['layer%d.B'%idx]=wrap.B.float().contiguous()
        safetensors.torch.save_file(accepted_state,str(candidate))
        target=OUT/('S%d.safetensors'%stage)
        os.replace(candidate,target)
        receipt={'status':'EXPERIMENTAL_ADAPTER_TRAINED','stage':stage,'layers':list(wrappers),'optimizer_steps':1,
                 'objective':'supervised_causal_lm_cross_entropy','training_loss_before':before,'training_loss_after':after,
                 'gpu_optimizer':'DirectML AdamW','cpu_model':'Qwen3.5-9B bf16 frozen','base_source_revision':m['source_revision'],
                 'source_data_sha256':sha(exfile),'sha256':sha(target),'timestamp':utc(),
                 'line_search_factor':factor,
                 'verified_heldout_performance':False,'ready_to_merge':False,'teacher_deleted':False}
        atomic_json(status_path,receipt)
        print('STAGE_EXPERIMENTAL_TRAINED',stage,'loss',before,'->',after,'SHA256',receipt['sha256'],flush=True)
        # Keep adapter active for subsequent stages, but clear each tap to reduce memory.
        for wrap in wrappers.values():wrap.tap=None;wrap.x=None
        # no deletion of original 9B weights or old NOX
    print('NOX_9B_EXPERIMENTAL_RUN_FINISHED',flush=True)

class ThermalStop(Exception):
    pass

def supervisor(cpu_python,gpu_python,script,limit):
    m,f,d=check_host()
    print('BASE_9B_VERIFIED',m['source_revision'],'data',len(d),'samples',flush=True)
    write_progress(read_sensor(),'WORKER_START')
    cmd=[str(cpu_python),str(script),'--cpu-worker','--gpu-python',str(gpu_python),'--stages',str(limit)]
    flags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
    attempts=0
    while True:
        proc=subprocess.Popen(cmd,creationflags=flags)
        highs=0
        try:
            while proc.poll() is None:
                try:t=read_sensor()
                except Exception as err:raise RuntimeError('SENSOR_LOST_HOLD: '+str(err))
                write_progress(t,'TRAINING_CPU_BACKBONE_GPU_LORA')
                print('NOX_SAFETY_HOTSPOT',round(t,1),'C',flush=True)
                if t>=75:raise ThermalStop('SAFE70_HARD_STOP >=75C')
                highs=highs+1 if t>=70 else 0
                if highs>=3:raise ThermalStop('SAFE70_STOP three consecutive readings >=70C')
                time.sleep(2)
            if proc.returncode:raise RuntimeError('9B training worker HOLD exit '+str(proc.returncode))
            write_progress(read_sensor(),'EXPERIMENTAL_CYCLE_FINISHED')
            print('NOX FORGE GPU WORKER FINISHED; check every stage receipt before promotion',flush=True)
            return
        except BaseException as error:
            if proc.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
                else:proc.kill()
            if not isinstance(error,ThermalStop):
                write_progress(None,'HOLD: '+str(error))
                raise
            attempts+=1
            write_progress(None,'SAFE70_COOLDOWN: '+str(error))
            print('SAFE70 STOP:',str(error),'Cooling 180 seconds; checkpoints preserved',flush=True)
            if attempts>3:raise RuntimeError('SAFE70_HOLD after 3 thermal restarts')
            time.sleep(180)
            for _ in range(3):
                t=read_sensor()
                if t>=65:raise RuntimeError('SAFE70_HOLD cooling insufficient: %.1fC'%t)
                time.sleep(2)
            print('SAFE70 RESUME: valid Hot Spot below 65C; restarting from last accepted stage',flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cpu-worker',action='store_true');ap.add_argument('--gpu-step',action='store_true');ap.add_argument('--gpu-python');ap.add_argument('--cpu-python');ap.add_argument('--stage',type=int);ap.add_argument('--packet');ap.add_argument('--output');ap.add_argument('--stages',type=int,default=8);ap.add_argument('--init-report',action='store_true')
    a=ap.parse_args()
    try:
        if a.init_report:
            print('NOX 9B PROGRESS:',OUT/'NOX_9B_GPU_PROGRESS.html','completed experimental segments:',write_progress(None,'PREPARING'))
        elif a.gpu_step:gpu_step(OUT,a.stage,a.packet,a.output)
        elif a.cpu_worker:train_cpu(Path(a.gpu_python),Path(__file__).resolve(),a.stages)
        else:supervisor(Path(a.cpu_python),Path(a.gpu_python),Path(__file__).resolve(),a.stages)
    except Exception as e:
        print('NOX_9B_HOLD:',type(e).__name__,str(e),file=sys.stderr,flush=True)
        return 1
    return 0
if __name__=='__main__':sys.exit(main())