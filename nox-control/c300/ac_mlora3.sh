echo "C300: ac_mlora3"
D=/workspace/nox/tmp/ml; mkdir -p $D
cat > $D/ml.py <<'PY'
import time,torch,sys,json
from transformers import AutoModelForCausalLM
from peft import LoraConfig,get_peft_model
torch.cuda.set_per_process_memory_fraction(0.1)
P='/workspace/nox/models/gpu/Qwen/Qwen3-0.6B'
m=AutoModelForCausalLM.from_pretrained(P,torch_dtype=torch.float16).cuda()
m.gradient_checkpointing_enable(); m.enable_input_require_grads()
cfg=LoraConfig(r=8,lora_alpha=16,target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'])
pm=get_peft_model(m,cfg,adapter_name='a0')
res={}
def mk(n):
    for i in range(1,n):
        if f'a{i}' not in pm.peft_config: pm.add_adapter(f'a{i}',cfg)
def run(n,mode,B=1,L=128,steps=3):
    names=[f'a{i}' for i in range(n)]
    for nm in names:
        pm.set_adapter(nm)
    params={nm:[p for k,p in pm.named_parameters() if f'.{nm}.' in k] for nm in names}
    # make all trainable
    for nm in names:
        for p in params[nm]: p.requires_grad_(True)
    opts={nm:torch.optim.AdamW(params[nm],lr=1e-4) for nm in names}
    x=torch.randint(0,150000,(B,L),device='cuda')
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    def step():
        if mode=='seq':
            for nm in names:
                pm.set_adapter(nm); out=pm(input_ids=x,labels=x); out.loss.backward(); opts[nm].step(); opts[nm].zero_grad(set_to_none=True)
        else:
            xb=x[:1].repeat(n,1)  # n samples, one per adapter
            out=pm(input_ids=xb,adapter_names=names,labels=xb); out.loss.backward()
            for nm in names: opts[nm].step(); opts[nm].zero_grad(set_to_none=True)
    step(); torch.cuda.synchronize(); t=time.time()
    for _ in range(steps): step()
    torch.cuda.synchronize(); dt=(time.time()-t)/steps
    return dt,torch.cuda.max_memory_allocated()/2**30
for n in (1,2,4,8,16,32):
    mk(n)
    for mode in ('seq','mix'):
        if mode=='mix' and n==1: continue
        try:
            dt,mem=run(n,mode); print(f'N={n} {mode} step {dt:.2f}s  per-adapter {dt/n:.2f}s  peak {mem:.2f}GiB',flush=True)
        except Exception as e:
            print(f'N={n} {mode} ERR {str(e)[:140]}',flush=True); torch.cuda.empty_cache()
            if 'out of memory' in str(e): sys.exit()
PY
setsid -f nice -n 19 taskset -c 4-7,20-23 /workspace/nox/venv/bin/python -I $D/ml.py > $D/ml.log 2>&1 </dev/null
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; sleep 200; grep -E "^N=|Error|error" $D/ml.log | tail -20; nvidia-smi --query-gpu=memory.used --format=csv,noheader
