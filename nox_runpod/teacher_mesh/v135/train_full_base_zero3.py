"""NOX V135: genuine full-base SFT distillation on existing GPU1, never LoRA.

Requires trusted signed native OneHost admission and original restored backups.
Uses existing Hugging Face Trainer/DeepSpeed ZeRO-3 CPU parameter + optimizer
offload, no new service, teacher process, paid GPU or student model creation.
Never automatically promotes resulting checkpoint to live NOX GGUF/P02.
"""
from __future__ import annotations
import argparse,hashlib,hmac,json,os,re,time,math
from pathlib import Path
from collections.abc import Mapping

from .zero3_fullbase_plan import fullbase_admission,zero3_cpu_config,sha256_manifest,STOP_PATHS
from .curate_teacher_distillation import _file_sha
from .verified_resume import admit_resume
from .maya_acceptance_gate import verify_maya_admission

INSTANCE=60509551
SIGN_ENV='NOX_EXISTING_ONEHOST_OWNER_HMAC'
_SHA=re.compile(r'^[0-9a-f]{64}$')
_ALLOWED_STEPS=(1,2,5,10,20,50,100,200,500,1000)

def _json(path:Path,max_size:int=80000)->dict:
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<max_size:
        raise RuntimeError('HOLD_EVIDENCE_INPUT_MISSING_OR_TOO_LARGE')
    try:data=json.loads(path.read_text(encoding='utf8'))
    except (ValueError,UnicodeDecodeError) as ex:raise RuntimeError('HOLD_EVIDENCE_JSON') from ex
    if not isinstance(data,dict):raise RuntimeError('HOLD_EVIDENCE_SCHEMA')
    return data

def verify_owner(native:dict,approval:dict,secret:bytes,now:int|None=None)->dict:
    if not isinstance(native,dict) or not isinstance(approval,dict):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    if not isinstance(secret,bytes) or len(secret)<32:
        raise RuntimeError('HOLD_OWNER_HMAC_KEY')
    needed={'action','instance_id','issued_at','expires_at','admission_sha256','signature'}
    if set(approval)!=needed or approval['action']!='nox.forge.fullbase.distill' or approval['instance_id']!=INSTANCE:
        raise RuntimeError('HOLD_OWNER_ACTION_INSTANCE')
    start,end=approval['issued_at'],approval['expires_at']
    if type(start) is not int or type(end) is not int or not 0<end-start<=300:
        raise RuntimeError('HOLD_OWNER_APPROVAL_TTL')
    ts=int(time.time()) if now is None else now
    if ts<start-30 or ts>=end:
        raise RuntimeError('HOLD_OWNER_APPROVAL_EXPIRED')
    source_sha=sha256_manifest(native)
    if approval['admission_sha256']!=source_sha or not _SHA.fullmatch(str(approval['signature'])):
        raise RuntimeError('HOLD_OWNER_SOURCE_PIN')
    signed={k:v for k,v in approval.items() if k!='signature'}
    payload=json.dumps(signed,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')
    expected=hmac.new(secret,payload,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,approval['signature']):
        raise RuntimeError('HOLD_OWNER_SIGNATURE')
    plan=fullbase_admission(native)
    if plan.get('state')!='READY_FOR_SIGNED_ONEHOST_TRAINING_START':
        raise RuntimeError('HOLD_LIVE_RESOURCE_ADMISSION')
    return plan

def verify_inputs(student:Path,data:Path,output:Path,native:dict,*,resume:bool=False)->dict:
    if student.is_symlink() or data.is_symlink() or not student.is_dir() or not data.is_dir():
        raise RuntimeError('HOLD_ORIGINAL_HF_OR_CORPUS_MISSING')
    if (output.is_symlink() or student==output or student in output.parents or data in output.parents
            or (output.exists() and not resume) or (resume and not output.is_dir())):
        raise RuntimeError('HOLD_OUTPUT_COLLISION')
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise RuntimeError('HOLD_CHECKPOINT_PARENT')
    manifest=_json(data/'manifest.json')
    if manifest.get('schema')!='NOX_V135_VERIFIED_TEACHER_DISTILL_CORPUS_V1':
        raise RuntimeError('HOLD_CORPUS_MANIFEST')
    if (manifest.get('source_groups_disjoint') is not True or
        manifest.get('train_rows',0)<300 or manifest.get('holdout_rows',0)<30):
        raise RuntimeError('HOLD_CORPUS_SOURCE_SPLIT')
    for part in ('train','holdout'):
        p=data/(part+'.jsonl')
        if not p.is_file() or p.is_symlink() or _file_sha(p)!=manifest.get(part+'_sha256'):
            raise RuntimeError('HOLD_DATASET_SHA')
        if _file_sha(p)!=native.get(part+'_dataset_sha256'):
            raise RuntimeError('HOLD_NATIVE_DATASET_PIN')
    for name in ('config.json','tokenizer_config.json'):
        p=student/name
        if not p.is_file() or p.is_symlink():raise RuntimeError('HOLD_HF_MODEL_CONFIG')
    shards=[p for p in student.glob('*.safetensors') if p.is_file() and not p.is_symlink()]
    if not shards or sum(p.stat().st_size for p in shards)!=native.get('student_shard_bytes'):
        raise RuntimeError('HOLD_HF_BASE_SHARDS')
    if not _SHA.fullmatch(str(native.get('student_base_sha256'))):
        raise RuntimeError('HOLD_HF_STUDENT_SHA')
    return manifest

def _stop_active(stop_file:Path)->bool:
    """Fail closed on any original OneHost or custom STOP sentinel.

    A dangling symlink counts as STOP, not as an absent sentinel. No secrets,
    extra service, GPU import or native write is needed for this check.
    """
    try:
        for name in dict.fromkeys((*STOP_PATHS,str(stop_file))):
            path=Path(name)
            if path.exists() or path.is_symlink():
                return True
    except OSError:
        return True
    return False


def _stop_callback(TrainerCallback,stop_file:Path):
    """Transformers lifecycle STOP + bounded checkpoint I/O.

    Keep first optimizer checkpoint, then save at most once per five minutes
    (measured after previous finished save), and at the final optimizer step.
    A STOP aborts before triggering a new save. No extra process or scheduler.
    """
    class _NOXStopCallback(TrainerCallback):
        def __init__(self):
            self._last_save_at=time.monotonic()
        def _check(self):
            if _stop_active(stop_file):
                raise RuntimeError('HOLD_STOP_DURING_TRAINING')
        def on_train_begin(self,args,state,control,**kwargs):
            self._check();self._last_save_at=time.monotonic();return control
        def on_epoch_begin(self,args,state,control,**kwargs):
            self._check();return control
        def on_step_begin(self,args,state,control,**kwargs):
            self._check();return control
        def on_substep_end(self,args,state,control,**kwargs):
            self._check();return control
        def on_step_end(self,args,state,control,**kwargs):
            self._check()
            step=getattr(state,'global_step',None)
            total=getattr(state,'max_steps',None)
            if type(step) is int and step>0 and (
                step==1 or (type(total) is int and step>=total)
                or time.monotonic()-self._last_save_at>=300
            ):
                control.should_save=True
            return control
        def on_prediction_step(self,args,state,control,**kwargs):
            self._check();return control
        def on_evaluate(self,args,state,control,**kwargs):
            self._check();return control
        def on_save(self,args,state,control,**kwargs):
            self._check();self._last_save_at=time.monotonic();return control
    return _NOXStopCallback()


def make_dataset(file:Path,tokenizer,max_len:int):
    from torch.utils.data import Dataset
    items=[]
    with file.open('rt',encoding='utf8') as src:
        for line in src:
            row=json.loads(line)
            if (row.get('rights_verified') is not True or
                row.get('privacy_approved') is not True or
                row.get('validation_passed') is not True):
                raise RuntimeError('HOLD_TEACHER_DATA_UNVERIFIED')
            prefix=tokenizer.apply_chat_template(
                [{'role':'user','content':row['prompt']}],
                tokenize=False,add_generation_prompt=True)
            a=tokenizer(prefix,add_special_tokens=False)['input_ids']
            b=tokenizer(row['completion']+(tokenizer.eos_token or ''),
                        add_special_tokens=False)['input_ids']
            a=a[-max(16,max_len//2):]
            b=b[:max_len-len(a)]
            if len(b)<3:raise RuntimeError('HOLD_TEACHER_LABEL_TRUNCATION')
            ids=a+b
            items.append({'input_ids':ids,'attention_mask':[1]*len(ids),
                          'labels':[-100]*len(a)+b})
    class Rows(Dataset):
        def __len__(self):return len(items)
        def __getitem__(self,i):return items[i]
    return Rows()


def validate_existing_v100_torch(torch_module)->dict:
    """P0 fail-closed ABI check before model load, allocations or checkpoint I/O.

    A visible SM70 device alone does not prove that an installed PyTorch
    wheel contains Volta kernels (notably newer CUDA 12.8/13.x wheels).
    Inspect the already-installed runtime: NEVER pip-install over live NOX.
    """
    cuda_build=getattr(getattr(torch_module,'version',None),'cuda',None)
    if not isinstance(cuda_build,str) or re.fullmatch(r'12\.\d+(?:\.\d+)?',cuda_build) is None:
        raise RuntimeError('HOLD_CUDA12_TORCH_BUILD')
    cuda=getattr(torch_module,'cuda',None)
    if cuda is None:
        raise RuntimeError('HOLD_V100_GPU1_SM70')
    try:
        visible=cuda.is_available()
        count=cuda.device_count()
        capability=tuple(cuda.get_device_capability(0)) if visible and count==1 else None
    except Exception as ex:
        raise RuntimeError('HOLD_V100_GPU1_SM70') from ex
    if visible is not True or count!=1 or capability!=(7,0):
        raise RuntimeError('HOLD_V100_GPU1_SM70')
    try:
        compiled_arches=cuda.get_arch_list()
    except Exception as ex:
        raise RuntimeError('HOLD_TORCH_WHEEL_SM70_ARCH') from ex
    if not isinstance(compiled_arches,(list,tuple)) or not any(
        name in compiled_arches for name in ('sm_70','compute_70')
    ):
        raise RuntimeError('HOLD_TORCH_WHEEL_SM70_ARCH')
    return {'torch_cuda_build':cuda_build,'compiled_sm70':True,
            'visible_v100_count':1,'precision':'fp16'}

def run(args)->dict:
    if args.max_steps not in _ALLOWED_STEPS or not 64<=args.max_tokens<=1024 or not 1<=args.accum<=128:
        raise RuntimeError('HOLD_STEPS_OR_BATCH_SCOPE')
    if not 0<float(args.lr)<=2e-5:
        raise RuntimeError('HOLD_LEARNING_RATE')
    if not args.execute or os.environ.get('NOX_ONEHOST_NATIVE_APPROVED')!='1':
        raise RuntimeError('HOLD_SIGNED_NATIVE_LAUNCH_REQUIRED')
    native=_json(Path(args.native))
    approval=_json(Path(args.approval),3000)
    signed_secret=os.environ.get(SIGN_ENV,'').encode('utf8')
    verify_owner(native,approval,signed_secret)
    # This exact accepted E2E receipt and live p0.training lease gate precede
    # input staging, GPU framework import, tokenizer access and model loading.
    maya_lineage=verify_maya_admission(native)
    student=Path(args.student).resolve()
    corpus_dir=Path(args.dataset).resolve()
    out=Path(args.output).resolve()
    resume_path=Path(args.resume_checkpoint).absolute() if getattr(args,'resume_checkpoint',None) else None
    manifest=verify_inputs(student,corpus_dir,out,native,resume=resume_path is not None)
    config=zero3_cpu_config(micro_batch=1,grad_accum=args.accum,learning_rate=float(args.lr))
    resumed=admit_resume(out,resume_path,native,max_steps=args.max_steps,expected_config=config) if resume_path else None
    if os.environ.get('CUDA_VISIBLE_DEVICES')!='1':
        raise RuntimeError('HOLD_GPU0_OWNER_CHAT_MUST_BE_RESERVED')
    if _stop_active(Path(args.stop_file)):
        raise RuntimeError('HOLD_STOP_ACTIVE')
    # Load GPU framework only AFTER all native admission, identity and restore gates.
    import torch
    p0_runtime=validate_existing_v100_torch(torch)
    import importlib.metadata as metadata
    for pkg in ('deepspeed','transformers','accelerate','safetensors'):
        try:metadata.version(pkg)
        except metadata.PackageNotFoundError as ex:
            raise RuntimeError('HOLD_DEPENDENCY_'+pkg.upper()) from ex
    from transformers import AutoTokenizer,AutoModelForCausalLM,Trainer,TrainingArguments,TrainerCallback
    config_path=out/'deepspeed_zero3_cpu.json'
    if not resumed:
        out.mkdir(mode=0o700)
        config_path.write_text(json.dumps(config,indent=2,sort_keys=True)+'\n',encoding='utf8')
        os.chmod(config_path,0o600)
    # Resume never alters the original DeepSpeed config or overwrites output.
    torch.manual_seed(3407)
    settings=TrainingArguments(
        output_dir=str(out),run_name='NOX_V135_ONE_STUDENT',
        overwrite_output_dir=False,
        per_device_train_batch_size=1,per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.accum,learning_rate=float(args.lr),
        fp16=True,bf16=False,deepspeed=str(config_path),
        max_steps=args.max_steps,gradient_checkpointing=True,
        logging_steps=1,eval_strategy='no',
        save_strategy='steps',save_steps=args.max_steps,save_total_limit=2,
        report_to='none',dataloader_num_workers=0,remove_unused_columns=False,
        save_safetensors=True,seed=3407)
    tok=AutoTokenizer.from_pretrained(str(student),local_files_only=True,trust_remote_code=False)
    if not getattr(tok,'chat_template',None):
        raise RuntimeError('HOLD_HF_TOKENIZER_CHAT_TEMPLATE')
    if tok.pad_token is None:
        if tok.eos_token is None:raise RuntimeError('HOLD_HF_TOKENIZER_PAD')
        tok.pad_token=tok.eos_token
    # ZeRO-3 is enabled by TrainingArguments before from_pretrained.
    model=AutoModelForCausalLM.from_pretrained(
        str(student),local_files_only=True,trust_remote_code=False,
        torch_dtype=torch.float16,attn_implementation='eager',low_cpu_mem_usage=True)
    if any(not p.requires_grad for p in model.parameters()):
        raise RuntimeError('HOLD_PARTIAL_WEIGHTS_DETECTED')
    if any(any(token in n.lower() for token in ('lora_','adapter','peft'))
           for n,_ in model.named_modules()):
        raise RuntimeError('HOLD_ADAPTER_DETECTED')
    model.config.use_cache=False
    train=make_dataset(corpus_dir/'train.jsonl',tok,args.max_tokens)
    held=make_dataset(corpus_dir/'holdout.jsonl',tok,args.max_tokens)
    def collate(rows):
        width=max(len(r['input_ids']) for r in rows)
        def tensor(key,pad):
            return torch.tensor([r[key]+[pad]*(width-len(r[key])) for r in rows],
                                dtype=torch.long)
        return {'input_ids':tensor('input_ids',tok.pad_token_id),
                'attention_mask':tensor('attention_mask',0),
                'labels':tensor('labels',-100)}
    trainer=Trainer(model=model,args=settings,train_dataset=train,
                    eval_dataset=held,data_collator=collate,processing_class=tok,
                    callbacks=[_stop_callback(TrainerCallback,Path(args.stop_file))])
    if _stop_active(Path(args.stop_file)):
        raise RuntimeError('HOLD_STOP_AFTER_MODEL_LOAD')
    before=trainer.evaluate(metric_key_prefix='holdout_before')
    if _stop_active(Path(args.stop_file)):
        raise RuntimeError('HOLD_STOP_BEFORE_TRAIN')
    result=trainer.train(resume_from_checkpoint=resumed['checkpoint'] if resumed else None)
    if _stop_active(Path(args.stop_file)):
        raise RuntimeError('HOLD_STOP_AFTER_TRAIN')
    steps=trainer.state.global_step
    if type(steps) is not int or steps<1 or (resumed and steps<=resumed['start_step']):
        raise RuntimeError('HOLD_REAL_OPTIMIZER_STEP')
    after=trainer.evaluate(metric_key_prefix='holdout_after')
    if _stop_active(Path(args.stop_file)):
        raise RuntimeError('HOLD_STOP_AFTER_EVALUATE')
    x=before.get('holdout_before_loss');y=after.get('holdout_after_loss')
    if not all(isinstance(z,(int,float)) and math.isfinite(z) and z>=0 for z in (x,y)):
        raise RuntimeError('HOLD_HOLDOUT_NONFINITE')
    checkpoints=[p for p in out.glob('checkpoint-*') if p.is_dir()]
    if not checkpoints:
        raise RuntimeError('HOLD_ZERO3_CHECKPOINT_NOT_WRITTEN')
    if _stop_active(Path(args.stop_file)):
        raise RuntimeError('HOLD_STOP_BEFORE_RECEIPT')
    receipt={
        'schema':'NOX_V135_NATIVE_BASE_WEIGHT_OPTIMIZER_LOCAL_RECEIPT_V1',
        **maya_lineage,
        'student_original_sha256':native['student_base_sha256'],
        'train_sha256':manifest['train_sha256'],
        'holdout_sha256':manifest['holdout_sha256'],
        'optimizer_steps_actual':steps,'trainer_global_step':result.global_step,
        'resumed_from_checkpoint':resumed['checkpoint'] if resumed else None,
        'resume_original_step':resumed['start_step'] if resumed else None,
        'resume_tree_sha256':resumed['checkpoint_sha256'] if resumed else None,
        'all_base_requires_grad':True,'uses_adapters':False,
        'deepspeed_zero3_cpu_offload':True,'gpu0_chat_untouched':True,
        'p0_existing_runtime_compat':p0_runtime,
        'holdout_before_loss':float(x),'holdout_after_loss':float(y),
        'checkpoint_dirs_created':len(checkpoints),
        'checkpoint_policy':'FIRST_STEP_OR_300_SECONDS_OR_FINAL',
        'new_checkpoint_external_restore_verified':False,
        'new_student_weights_sha_delta_verified':False,
        'original_live_weights_unchanged':True,'original_s03_unchanged':True,
        'production_promoted':False,'release_state':'HOLD_INDEPENDENT_CHECKPOINT_RESTORE'
    }
    record=out/(f'NOX_V135_RESUME_STEP_{steps}_RECEIPT.json' if resumed
                else 'NOX_V135_LOCAL_OPTIMIZER_RECEIPT.json')
    if record.exists():raise RuntimeError('HOLD_EXISTING_RECEIPT')
    with record.open('x',encoding='utf8') as file:
        os.chmod(record,0o600);json.dump(receipt,file,sort_keys=True,indent=2);file.write('\n')
    return {'state':'LOCAL_OPTIMIZER_STEPS_NEED_OFFSITE_RESTORE',
            'optimizer_steps_actual':steps,'active_model_changed':False,
            'receipt_sha256':_file_sha(record)}

def main():
    p=argparse.ArgumentParser()
    for arg in ('student','dataset','native','approval','output'):
        p.add_argument('--'+arg,required=True)
    p.add_argument('--max-steps',type=int,default=1)
    p.add_argument('--max-tokens',type=int,default=256)
    p.add_argument('--accum',type=int,default=16)
    p.add_argument('--lr',type=float,default=5e-6)
    p.add_argument('--resume-checkpoint',default=None)
    p.add_argument('--stop-file',default='/root/nox/STOP')
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    try:result=run(args)
    except Exception as ex:
        reason=str(ex)
        print(json.dumps({'state':'HOLD_NO_NATIVE_OPTIMIZER_PASS',
            'reason':reason if reason.startswith('HOLD_') and len(reason)<130 else type(ex).__name__,
            'optimizer_steps_verified':0,'live_weights_changed':False}))
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
