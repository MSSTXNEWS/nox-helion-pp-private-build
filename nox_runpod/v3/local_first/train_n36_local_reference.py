# NOX-36 SFT: Qwen3.6-35B-A3B, routed experts frozen in NF4 (custom packed 4-bit, dequant per layer on the fly),
# LoRA r64 (bf16) on full-attn q/k/v/o + GatedDeltaNet in_proj_qkv/z/out_proj + shared_expert (expert-aware) ;
# router aux loss (output_router_logits); vision tower frozen & dropped from GPU; ckpt every SAVE_MIN to /workspace/nox36/ckpt; resumable.
import json, torch, time, math, random, os, sys, hashlib, re
sys.path.insert(0,os.environ.get('NOX_SEED_PATH','/root/nox_local/seed'))
from common import student_system
import bitsandbytes.functional as BF
from transformers import AutoTokenizer, AutoConfig
from transformers.models.qwen3_5_moe import modeling_qwen3_5_moe as MM
from peft import LoraConfig, get_peft_model, set_peft_model_state_dict
from safetensors.torch import load_file
W=os.environ.get('NOX_WORKDIR','/root/nox_local'); BASE=os.environ.get('BASE','/dev/shm/base36'); CK=f'{W}/ckpt'; os.makedirs(CK,exist_ok=True)
LR=float(os.environ.get('LR','1e-4')); TOKB=int(os.environ.get('TOKB','32000')); MB=int(os.environ.get('MB','8192')); SAVE_MIN=float(os.environ.get('SAVE_MIN','20'))
BK=int(os.environ.get('BK','512')); MAXSTEPS=int(os.environ.get('MAXSTEPS','0')); MAXROWS=int(os.environ.get('MAXROWS','0')); AUX=float(os.environ.get('AUX','0.001'))
RUN=os.environ.get('RUN','sft'); CKR=f'{CK}/{RUN}'; os.makedirs(CKR,exist_ok=True)
log=open(f'{W}/logs/train_{RUN}.log','a')
def L(*a):
    s=time.strftime('%H:%M:%S')+' '+' '.join(map(str,a)); print(s,flush=True); log.write(s+'\n'); log.flush()
tok=AutoTokenizer.from_pretrained(BASE)
# ---- data: pre-tokenized by prep_n36.py (96-core), kept in RAM; priority token budget ----
TD=os.environ.get('TD',f'{W}/data/tok'); DT=torch.load(f'{TD}/train.pt'); hold=torch.load(f'{TD}/hold.pt')
train=DT['train']; srcs=DT['src']; BUD=int(os.environ.get('TRAIN_TOK','0'))
CORE=('s2','judged_keep','s1_kept','w3','s3','hf01_selfreflect','anchor')
idx=list(range(len(train))); random.Random(42).shuffle(idx)
if BUD:
    core=[i for i in idx if srcs[i] in CORE]; rest=[i for i in idx if srcs[i] not in CORE]; sel=[]; t=0
    for i in core+rest:
        n=len(train[i][0])+len(train[i][1])
        if t+n>BUD: continue
        sel.append(i); t+=n
    idx=sel; random.Random(43).shuffle(idx)
PLAN=f'{CKR}/plan.json'
if os.path.exists(PLAN): plan=json.load(open(PLAN))
else:
    plan=[];cur=[];tk=0
    for j in idx:
        cur.append(j); tk+=len(train[j][0])+len(train[j][1])
        if tk>=TOKB: plan.append(cur);cur=[];tk=0
    if cur: plan.append(cur)
    json.dump(plan,open(PLAN,'w'))
TOTAL=len(plan) if not MAXSTEPS else min(MAXSTEPS,len(plan))
import collections as _c; L('mix groups',_c.Counter(srcs[j] for st_ in plan for j in st_).most_common())
L(f'NOX36 {RUN} start rows={sum(len(x) for x in plan)} tokens={sum(len(train[j][0])+len(train[j][1]) for st_ in plan for j in st_)} holdout={len(hold)} steps={TOTAL}/{len(plan)} MB={MB} TOKB={TOKB}')
def encode(x): return x
# ---- model: NF4-packed routed experts ----
class QExperts(torch.nn.Module):
    def __init__(self, ex):
        super().__init__(); self.E=ex.num_experts; self.act_fn=ex.act_fn
        gu=ex.gate_up_proj.data.to('cuda',torch.bfloat16); self.gu_q,self.gu_s=BF.quantize_4bit(gu,quant_type='nf4',blocksize=64,compress_statistics=True); del gu
        dn=ex.down_proj.data.to('cuda',torch.bfloat16); self.dn_q,self.dn_s=BF.quantize_4bit(dn,quant_type='nf4',blocksize=64,compress_statistics=True); del dn
    def forward(self, x, top_k_index, top_k_weights):
        Wgu=BF.dequantize_4bit(self.gu_q,self.gu_s); Wdn=BF.dequantize_4bit(self.dn_q,self.dn_s)
        T,k=top_k_index.shape; e=top_k_index.reshape(-1); order=torch.argsort(e,stable=True)
        tok_idx=(torch.arange(T,device=x.device).repeat_interleave(k))[order]; w=top_k_weights.reshape(-1)[order]
        counts=torch.bincount(e,minlength=self.E).tolist(); xs=x[tok_idx]; outs=[]; s0=0
        for ei,c in enumerate(counts):
            if c==0: continue
            xi=xs[s0:s0+c]; g,u=torch.nn.functional.linear(xi,Wgu[ei]).chunk(2,dim=-1)
            outs.append(torch.nn.functional.linear(self.act_fn(g)*u,Wdn[ei])); s0+=c
        y=torch.cat(outs,0)*w[:,None].to(x.dtype)
        out=torch.zeros_like(x); out.index_add_(0,tok_idx,y.to(x.dtype)); return out
t_load=time.time()
cfg=AutoConfig.from_pretrained(BASE)
model=MM.Qwen3_5MoeForConditionalGeneration.from_pretrained(BASE,config=cfg,dtype=torch.bfloat16,device_map='cpu',attn_implementation='sdpa')
L('cpu loaded sec',round(time.time()-t_load))
try: del model.model.visual
except Exception as e: L('visual keep',e)
for i,layer in enumerate(model.model.language_model.layers):
    ex=layer.mlp.experts; layer.mlp.experts=QExperts(ex); del ex
model.to('cuda'); import gc; gc.collect(); torch.cuda.empty_cache()
for p_ in model.parameters(): p_.requires_grad_(False)
L('model on GPU sec',round(time.time()-t_load),'mem GB',round(torch.cuda.memory_allocated()/1e9,2))
TM=r'.*language_model\.layers\.\d+\.(self_attn\.(q_proj|k_proj|v_proj|o_proj)|linear_attn\.(in_proj_qkv|in_proj_z|out_proj)|mlp\.shared_expert\.(gate_proj|up_proj|down_proj))'
model=get_peft_model(model,LoraConfig(r=64,lora_alpha=128,lora_dropout=0.05,target_modules=TM))
model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False}); model.enable_input_require_grads(); model.train()
core=model.base_model.model; lm_head=core.lm_head; inner=core.model
params=[p for p in model.parameters() if p.requires_grad]; L('trainable M',round(sum(p.numel() for p in params)/1e6,1))
import bitsandbytes as bnb
opt=bnb.optim.PagedAdamW8bit(params,lr=LR,weight_decay=0.0,betas=(0.9,0.99))
from liger_kernel.transformers.fused_linear_cross_entropy import LigerFusedLinearCrossEntropyLoss
LCE=LigerFusedLinearCrossEntropyLoss(reduction='sum')
NE=cfg.text_config.num_experts; TK=cfg.text_config.num_experts_per_tok
step=0
if os.path.exists(f'{CKR}/last/STEP'):
    step=int(open(f'{CKR}/last/STEP').read()); set_peft_model_state_dict(model,load_file(f'{CKR}/last/adapter_model.safetensors'))
    if os.path.exists(f'{CKR}/last/opt.pt'): opt.load_state_dict(torch.load(f'{CKR}/last/opt.pt',map_location='cuda'))
    L('RESUMED from step',step)
def lr_at(s):
    warm=min(1,(s+1)/20); return LR*warm*(0.1+0.9*0.5*(1+math.cos(math.pi*min(1,s/TOTAL))))
def save(tag):
    d=f'{CKR}/{tag}'; tmp=d+'.tmp'; model.save_pretrained(tmp); torch.save(opt.state_dict(),tmp+'/opt.pt'); open(tmp+'/STEP','w').write(str(step))
    if os.path.exists(d+'.prev'): os.system(f'rm -rf "{d}.prev"')   # only our own rotating previous checkpoint
    if os.path.exists(d): os.replace(d,d+'.prev')
    os.replace(tmp,d)
def nll(ps):
    model.eval(); tot=0.0; n=0
    with torch.no_grad():
        for pre,resp in ps:
            ids=torch.tensor([pre+resp]).cuda()
            h=inner(input_ids=ids).last_hidden_state[0,len(pre)-1:len(pre)+len(resp)-1]
            tot+=torch.nn.functional.cross_entropy(lm_head(h).float(),ids[0,len(pre):],reduction='sum').item(); n+=len(resp)
    model.train(); return tot/max(n,1)
def aux_loss(rl,att):
    try: return MM.load_balancing_loss_func(rl,NE,TK,att)
    except Exception: return MM.load_balancing_loss_func(rl,NE,TK)
if os.environ.get('EVAL0')=='1': L('base holdout nll',round(nll(hold[:40]),4))
t0=time.time(); tlast=time.time(); toks=0; s_start=step
while step<TOTAL:
    if os.path.exists(f'{W}/STOP_{RUN}'): L('STOP file -> save and exit'); save('last'); sys.exit(0)
    b=[train[j] for j in plan[step]]; b.sort(key=lambda x:len(x[0])+len(x[1]))
    ntok=sum(len(r) for _,r in b); loss_s=0.0; aux_s=0.0
    for g in opt.param_groups: g['lr']=lr_at(step)
    mbs=[];cur=[];c=0
    for x in b:
        cur.append(x); c+=len(x[0])+len(x[1])
        if c>=MB: mbs.append(cur);cur=[];c=0
    if cur: mbs.append(cur)
    for mb in mbs:
        Lm=max(len(a)+len(r) for a,r in mb); Lm=((Lm+BK-1)//BK)*BK
        ids=torch.full((len(mb),Lm),tok.pad_token_id or 0); att=torch.zeros((len(mb),Lm),dtype=torch.long)
        for r_,(a,r) in enumerate(mb): s=a+r; ids[r_,:len(s)]=torch.tensor(s); att[r_,:len(s)]=1
        ids=ids.cuda(); att=att.cuda()
        o=inner(input_ids=ids,attention_mask=att,output_router_logits=AUX>0); h=o.last_hidden_state
        loss=0.0
        for r_,(a,r) in enumerate(mb):
            hs_=h[r_,len(a)-1:len(a)+len(r)-1]
            loss=loss+LCE(lm_head.weight,hs_,ids[r_,len(a):len(a)+len(r)])
        tot=loss/ntok
        if AUX>0 and getattr(o,'router_logits',None):
            al=aux_loss(o.router_logits,att)*AUX*len(mb)/max(1,sum(len(m) for m in mbs)); tot=tot+al; aux_s+=float(al)
        tot.backward(); loss_s+=loss.detach()
    torch.nn.utils.clip_grad_norm_(params,1.0); opt.step(); opt.zero_grad(set_to_none=True); step+=1; toks+=sum(len(a)+len(r) for a,r in b)
    el=(time.time()-t0)/60
    if step%5==0 or step-s_start<=3:
        spm=(step-s_start)/el if el>0 else 0; eta=(TOTAL-step)/spm if spm>0 else -1
        L(f'step {step}/{TOTAL} loss {float(loss_s)/ntok:.4f} aux {aux_s:.4f} lr {lr_at(step):.2e} elapsed {el:.1f}m tok/s {toks/(el*60+1e-9):.0f} ETA {eta:.0f}m mem {torch.cuda.max_memory_allocated()/1e9:.1f}GB')
        json.dump({'run':RUN,'step':step,'total':TOTAL,'loss':float(loss_s)/ntok,'elapsed_min':el,'eta_min':eta,'tok_s':toks/(el*60+1e-9),'time':time.strftime('%H:%M:%S'),'pid':os.getpid()},open(f'{W}/status_{RUN}.json','w'))
    if (time.time()-tlast)/60>=SAVE_MIN:
        save('last'); tlast=time.time(); L('CKPT saved step',step)
        if os.environ.get('EVAL','1')=='1': L('holdout nll',round(nll(hold[:40]),4),'step',step)
save('last'); model.save_pretrained(f'{CKR}/final'); L('final holdout nll',round(nll(hold[:100]),4))
with model.disable_adapter(): L('base holdout nll',round(nll(hold[:100]),4))
open(f'{CKR}/DONE','w').write(str(step)); L('TRAIN_DONE',step)
