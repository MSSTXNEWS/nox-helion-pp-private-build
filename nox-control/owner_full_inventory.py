#!/usr/bin/env python3
"""Six bounded native read probes; only a private inventory receipt is written.

Never loads weights, imports native modules, deserializes optimizer pickles,
changes a service, generates a model answer, promotes a checkpoint or deletes
data. Installed files, source wiring and verified weight updates are distinct.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import struct
import subprocess
import tempfile
import time
import urllib.request
import urllib.parse

ROOT=Path('/root/nox')
PROC=Path('/proc')
SCHEMA='NOX_OWNER_FULL_INVENTORY_V1'
SMALL=1024*1024
SHA=re.compile(r'^[a-f0-9]{64}$')
NAME=re.compile(r'^[A-Za-z0-9_.:/+@ -]{1,300}$')
CHECKPOINT_FILES=('trainer_state.json','optimizer.pt','scheduler.pt','rng_state.pth',
                  'scaler.pt','adapter_config.json','adapter_model.safetensors')
PACKAGE_NAMES=('torch','transformers','accelerate','datasets','safetensors','peft',
               'bitsandbytes','trl','deepspeed','psutil','nvidia-ml-py','faiss-cpu',
               'sentence-transformers','sqlite-vec','fastapi','httpx','av')
SOURCE_NAMES=('chat_proxy','agent_loop','owner_chat_stream','owner_chat_ui',
              'nox_v29_chat_bridge','nox_v125_live_readonly','nox_v137_owner_self_observation',
              'slim_chat_t885u','s03_memory','nox_memory','nox_cores_t899u','emotion_cedr',
              'nox_tools','nox_admin','nox_agent_pool_t858u','nox_dispatcher_t855u',
              'owner_dispatcher_mentor','owner_component_tasks','owner_media_runtime',
              'hybrid_training_entry','train_qlora_35b_t866u','nox_priority_scheduler',
              'nox_autoscale_t877u','nox_pc_export','nox_cold_drive')
CREDENTIAL_NAMES=('OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY')


def emit(kind,value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},ensure_ascii=False,
                                      separators=(',',':'),allow_nan=False),flush=True)


def label(value):
    return value if (isinstance(value,str) and NAME.fullmatch(value) and not re.search(
        r'https?://[^/\s]*@|(?:hf_|ghp_|github_pat_|sk-proj-)[A-Za-z0-9_-]{12,}|Bearer\s',value,re.I)) else None


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def bounded(path,limit=SMALL,allow_link=False):
    path=Path(path)
    flags=os.O_RDONLY|os.O_NONBLOCK|(0 if allow_link else os.O_NOFOLLOW)
    fd=os.open(path,flags)
    with os.fdopen(fd,'rb') as file:
        meta=os.fstat(file.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size>limit:
            raise ValueError('BOUNDED_FILE_LIMIT')
        raw=file.read(limit+1)
        if len(raw)>limit:raise ValueError('BOUNDED_FILE_LIMIT')
        return raw,meta


def document(path,limit=SMALL):
    raw,meta=bounded(path,limit)
    return json.loads(raw),meta,hashlib.sha256(raw).hexdigest()


def optional_json(path,limit=SMALL):
    try:return document(path,limit)[0]
    except (OSError,ValueError,UnicodeError):return None


def allowed_model_path(path):
    try:
        resolved=Path(path).resolve(strict=True)
        return resolved if any(resolved.is_relative_to(base) for base in
                               (ROOT,Path('/workspace'),Path('/dev/shm'))) else None
    except (OSError,RuntimeError):return None


def file_record(path,hash_small=False):
    path=Path(path)
    row={'path':str(path),'present':False}
    try:
        meta=path.lstat();row['symlink']=stat.S_ISLNK(meta.st_mode)
        resolved=allowed_model_path(path)
        if resolved is None:return dict(row,state='UNRESOLVED_OR_OUTSIDE_ALLOWED_ROOTS')
        target=resolved.stat()
        if not stat.S_ISREG(target.st_mode):return dict(row,state='NOT_REGULAR_FILE')
        row.update(present=True,bytes=target.st_size,mtime_ns=target.st_mtime_ns,
                   device=target.st_dev,inode=target.st_ino,resolved_path=str(resolved))
        if hash_small and target.st_size<=SMALL:
            raw,_=bounded(resolved);row['sha256']=hashlib.sha256(raw).hexdigest()
            row['sha256_scope']='CURRENT_COMPLETE_SMALL_FILE'
        else:row['sha256_scope']='NOT_REHASHED'
    except OSError:row['state']='UNAVAILABLE'
    return row


def walk(roots,*,max_files=5000,max_dirs=700,seconds=5):
    """No directory symlinks; a global entry/time budget across explicit roots."""
    deadline=time.monotonic()+seconds;pending=list(reversed([Path(p) for p in roots]));files=[];seen=set();dirs=0;limited=False
    while pending and dirs<max_dirs and len(files)<max_files and time.monotonic()<deadline:
        path=pending.pop()
        try:
            if path.is_symlink() or not path.is_dir():continue
            identity=(path.stat().st_dev,path.stat().st_ino)
            if identity in seen:continue
            seen.add(identity);dirs+=1
            with os.scandir(path) as entries:
                for entry in entries:
                    if len(files)>=max_files or time.monotonic()>=deadline:limited=True;break
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in ('.git','__pycache__','node_modules','site-packages','logs','datasets','data'):
                            pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False) or entry.is_symlink():
                        files.append(Path(entry.path))
        except OSError:continue
    return files,{'directories':dirs,'files':len(files),'truncated':limited or bool(pending) or len(files)>=max_files}


def command(argv,timeout=5):
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout,shell=False)
        return result.returncode,result.stdout[:100000]
    except (OSError,subprocess.TimeoutExpired):return None,''


def local_json(port,path,timeout=3):
    started=time.monotonic()
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:'+str(port)+path,timeout=timeout) as response:
            raw=response.read(SMALL+1)
            if len(raw)>SMALL:raise ValueError('HTTP_SIZE_LIMIT')
            return response.status,json.loads(raw),round(time.monotonic()-started,4)
    except Exception as error:
        return getattr(error,'code',None),None,round(time.monotonic()-started,4)


def supervisor():
    rc,text=command(['supervisorctl','status'])
    rows=[]
    for line in text.splitlines()[:180]:
        match=re.match(r'^(nox[-_.][A-Za-z0-9_.:-]{1,100})\s+(RUNNING|STOPPED|EXITED|FATAL|STARTING|STOPPING|BACKOFF)\b(?:\s+pid\s+(\d+))?',line)
        if match:rows.append({'service':match[1],'state':match[2],
                             'pid':int(match[3]) if match[3] else None})
    return {'query_rc':rc,'services':rows}


def process_rows(owners):
    rows=[];raw={};deadline=time.monotonic()+4
    settings={'-m','--model','--port','-t','--threads','--threads-batch','-tb','-np','--parallel',
              '-c','--ctx-size','-ngl','--n-gpu-layers','--gpu-layers','--n-cpu-moe','-ncmoe',
              '--override-tensor','-ot','--cache-type-k','--cache-type-v','-ctk','-ctv'}
    booleans={'--cpu-moe','--no-mmap','--mlock','--flash-attn'}
    try:entries=list(PROC.iterdir())
    except OSError:return []
    for path in entries[:12000]:
        if time.monotonic()>deadline:break
        if not path.name.isdigit():continue
        try:
            state=(path/'stat').read_text().rsplit(') ',1)[1].split()
            argv=(path/'cmdline').read_bytes()[:65536].decode(errors='replace').strip('\0').split('\0')
            row={'pid':int(path.name),'ppid':int(state[1]),'start_ticks':int(state[19]),
                 'priority':int(state[15]),'nice':int(state[16]),'threads':int(state[17]),
                 'state':state[0],'rss_bytes':int(state[21])*os.sysconf('SC_PAGE_SIZE')}
            raw[row['pid']]=row
            if not argv or not any(word in ' '.join(argv[:3]) for word in ('nox','llama','train','ComfyUI')):continue
            row['executable']=label(Path(argv[0]).name)
            row['scripts']=[v for v in argv[1:4] if v.endswith(('.py','.sh')) and
                            v.startswith(('/root/nox/','/root/nox_selfheal','/opt/supervisor-scripts/')) and label(v)]
            chosen={}
            for index,arg in enumerate(argv):
                flag,separator,value=arg.partition('=')
                if flag in settings:
                    item=value if separator else (argv[index+1] if index+1<len(argv) else '')
                    chosen[flag]=label(item)
                elif flag in booleans:chosen[flag]=True
            row['settings']=chosen
            status=(path/'status').read_text()
            match=re.search(r'^NSpid:\s*(.*)$',status,re.M)
            row['namespace_pids']=[int(v) for v in match[1].split()] if match else []
            # Read only allowlisted scheduling/CUDA values; never return environ.
            environment=(path/'environ').read_bytes()[:100000].split(b'\0')
            allowed={}
            for field in environment:
                key,_,value=field.partition(b'=')
                if key in (b'CUDA_VISIBLE_DEVICES',b'OMP_NUM_THREADS',b'MKL_NUM_THREADS',b'OPENBLAS_NUM_THREADS'):
                    decoded=value.decode(errors='replace')
                    if re.fullmatch(r'[0-9, -]{0,50}',decoded):allowed[key.decode()]=decoded
            row['resource_environment']=allowed
            if int((path/'stat').read_text().rsplit(') ',1)[1].split()[19])!=row['start_ticks']:continue
            rows.append(row)
        except (OSError,ValueError,IndexError):continue
    roots={row['pid']:row['service'] for row in owners['services'] if row.get('pid')}
    for row in rows:
        pid=row['pid'];visited=set()
        for _ in range(16):
            if pid in roots:row['supervisor_owner']=roots[pid];break
            if pid in visited or pid not in raw:break
            visited.add(pid);pid=raw[pid]['ppid']
        row.setdefault('supervisor_owner','UNKNOWN')
    return rows[:160]


class GGUFReader:
    TYPES={0:('B',1),1:('b',1),2:('H',2),3:('h',2),4:('I',4),5:('i',4),
           6:('f',4),7:('?',1),10:('Q',8),11:('q',8),12:('d',8)}
    def __init__(self,file):
        meta=os.fstat(file.fileno())
        if not stat.S_ISREG(meta.st_mode):raise ValueError('GGUF_NOT_REGULAR')
        self.file=file;self.size=meta.st_size;self.values=0
    def take(self,n):
        if n<0 or self.file.tell()+n>min(self.size,16*SMALL):raise ValueError('GGUF_HEADER_BOUND')
        data=self.file.read(n)
        if len(data)!=n:raise ValueError('GGUF_TRUNCATED')
        return data
    def skip(self,n):
        if n<0 or self.file.tell()+n>min(self.size,16*SMALL):raise ValueError('GGUF_HEADER_BOUND')
        self.file.seek(n,1)
    def integer(self,fmt):return struct.unpack('<'+fmt,self.take(struct.calcsize(fmt)))[0]
    def string(self,keep=False):
        size=self.integer('Q')
        if keep:
            if size>1024:raise ValueError('GGUF_STRING_BOUND')
            return self.take(size).decode('utf-8')
        self.skip(size)
    def value(self,kind,keep=False,depth=0):
        self.values+=1
        if depth>4 or self.values>200000:raise ValueError('GGUF_VALUE_BOUND')
        if kind in self.TYPES:
            fmt,size=self.TYPES[kind]
            if keep:return self.integer(fmt)
            self.skip(size);return
        if kind==8:return self.string(keep)
        if kind!=9:raise ValueError('GGUF_UNKNOWN_TYPE')
        element=self.integer('I');count=self.integer('Q')
        if count>200000:raise ValueError('GGUF_ARRAY_BOUND')
        if element in self.TYPES:
            self.skip(self.TYPES[element][1]*count);return
        if element not in (8,9):raise ValueError('GGUF_UNKNOWN_TYPE')
        for _ in range(count):self.value(element,False,depth+1)


def gguf_metadata(path):
    allowed={'general.architecture','general.name','general.file_type','general.quantization_version',
             'general.parameter_count','general.basename','general.size_label'}
    endings=('.context_length','.embedding_length','.block_count','.expert_count','.expert_used_count',
             '.attention.head_count','.attention.head_count_kv','.feed_forward_length')
    result={'state':'UNKNOWN','metadata':{},'full_tensor_hash_verified':False}
    try:
        resolved=allowed_model_path(path)
        if resolved is None:raise ValueError('GGUF_PATH')
        fd=os.open(resolved,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as file:
            parser=GGUFReader(file)
            if parser.take(4)!=b'GGUF':raise ValueError('GGUF_MAGIC')
            version=parser.integer('I')
            if version not in (2,3):raise ValueError('GGUF_VERSION')
            tensors=parser.integer('Q');fields=parser.integer('Q')
            if fields>4096:raise ValueError('GGUF_KV_BOUND')
            result.update(version=version,tensor_count=tensors,metadata_fields=fields)
            for _ in range(fields):
                key=parser.string(True);kind=parser.integer('I')
                keep=(key in allowed or key.endswith(endings)) and not key.startswith('tokenizer.')
                value=parser.value(kind,keep)
                if keep and (isinstance(value,str) and label(value) or type(value) in (int,bool) or
                             type(value) is float and math.isfinite(value)):
                    result['metadata'][key]=value
            result.update(state='HEADER_OBSERVED',header_bytes_read_or_skipped=parser.file.tell())
    except (OSError,ValueError,UnicodeError,struct.error) as error:
        result['reason']=str(error) if str(error).startswith('GGUF_') else type(error).__name__
    return result


def mapped_models(pid):
    rows=[]
    try:
        with (PROC/str(pid)/'maps').open('r') as file:
            for line in file.read(2*SMALL).splitlines():
                fields=line.split(None,5)
                if len(fields)!=6 or '.gguf' not in fields[5]:continue
                path=fields[5].removesuffix(' (deleted)')
                if not path.startswith(('/root/nox/','/workspace/','/dev/shm/')) or not label(path):continue
                major,minor=fields[3].split(':')
                row={'path':path,'inode':int(fields[4]),'device':os.makedev(int(major,16),int(minor,16)),
                     'deleted':fields[5].endswith(' (deleted)'),'evidence':'LIVE_PROCESS_MAPPING'}
                if row not in rows:rows.append(row)
    except (OSError,ValueError):pass
    try:
        for fd in list((PROC/str(pid)/'fd').iterdir())[:512]:
            name=os.readlink(fd)
            if '.gguf' not in name:continue
            path=name.removesuffix(' (deleted)')
            if not path.startswith(('/root/nox/','/workspace/','/dev/shm/')) or not label(path):continue
            meta=fd.stat();row={'path':path,'inode':meta.st_ino,'device':meta.st_dev,
                               'deleted':name.endswith(' (deleted)'),'evidence':'LIVE_PROCESS_FD'}
            if not any(r['inode']==row['inode'] and r['device']==row['device'] for r in rows):rows.append(row)
    except OSError:pass
    return rows[:24]


def active_model():
    owners=supervisor();processes=process_rows(owners)
    servers=[row for row in processes if row['settings'].get('--port')=='8081']
    result={'state':'OBSERVED','services':owners,'model_processes':servers,
            'current_pointer':file_record(ROOT/'models/current.gguf'),'model_api':{}}
    paths={ROOT/'models/current.gguf'}
    for row in servers:
        candidate=row['settings'].get('--model',row['settings'].get('-m'))
        if candidate and candidate.endswith('.gguf'):
            record=file_record(candidate);row['argument_model']=record;paths.add(Path(candidate))
            maps=mapped_models(row['pid']);row['mapped_models']=maps
            row['loaded_inode_matches_argument']=any(
                r['inode']==record.get('inode') and r['device']==record.get('device') and not r['deleted'] for r in maps)
            row['loaded_identity_evidence']='MAPPED_INODE_MATCH' if row['loaded_inode_matches_argument'] else 'ARGUMENT_ONLY_UNVERIFIED'
    for endpoint in ('/health','/v1/models','/props','/slots'):
        code,data,elapsed=local_json(8081,endpoint)
        clean={'http':code,'seconds':elapsed}
        if endpoint=='/v1/models' and isinstance(data,dict):
            clean['models']=[{k:label(row.get(k)) for k in ('id','name','object') if label(row.get(k))}
                             for row in data['data'][:10] if isinstance(row,dict)] if isinstance(data.get('data'),list) else []
        elif endpoint=='/props' and isinstance(data,dict):
            clean['values']={k:number(data[k]) for k in ('total_slots','n_ctx','n_ctx_train') if k in data}
            settings=data.get('default_generation_settings') or {}
            if isinstance(settings,dict):clean['generation']={k:number(settings[k]) for k in ('n_ctx','n_predict','seed') if k in settings}
            clean['chat_template_present']=isinstance(data.get('chat_template'),str) and bool(data['chat_template'])
        elif endpoint=='/slots' and isinstance(data,list):
            clean['slots']=[{k:v for k,v in row.items() if k in ('id','n_ctx','is_processing','processing') and type(v) in (int,float,bool)} for row in data[:32] if isinstance(row,dict)]
        result['model_api'][endpoint]=clean
    files,coverage=walk((ROOT/'models',ROOT/'progress_pull_t784u/gguf',ROOT/'gguf',ROOT/'weights'),max_files=1800,seconds=3)
    candidates=[p for p in files if p.name.endswith('.gguf')]
    result['gguf_candidates']=[dict(file_record(p),gguf=gguf_metadata(p)) for p in sorted(set(candidates)|paths)[:45]]
    result['coverage']=coverage
    result['promotion_evidence']='UNKNOWN_UNTIL_EXACT_CHECKPOINT_EXPORT_PROVENANCE_VERIFIED'
    return result


def selected(obj,keys):
    if not isinstance(obj,dict):return {}
    result={}
    for key in keys:
        value=obj.get(key)
        if type(value) is bool or number(value) is not None:result[key]=value
        elif label(value):result[key]=value
        elif isinstance(value,list) and len(value)<=150:
            safe=[v for v in value if label(v) or number(v) is not None]
            if len(safe)==len(value):result[key]=safe
    return result


def tensor_header(path):
    result={'state':'UNKNOWN','tensor_values_read':False}
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as file:
            meta=os.fstat(file.fileno())
            if not stat.S_ISREG(meta.st_mode):raise ValueError('HEADER_NOT_REGULAR')
            prefix=file.read(8)
            if len(prefix)!=8:raise ValueError('HEADER')
            size=struct.unpack('<Q',prefix)[0]
            if size>SMALL or size>meta.st_size-8:raise ValueError('HEADER')
            document=json.loads(file.read(size))
        if not isinstance(document,dict):raise ValueError('HEADER')
        shapes=[];dtypes={};elements=0
        for name,value in document.items():
            if name=='__metadata__':continue
            if not isinstance(value,dict) or not isinstance(name,str) or len(name)>500:raise ValueError('HEADER')
            shape=value.get('shape');dtype=value.get('dtype');offset=value.get('data_offsets')
            if (not isinstance(shape,list) or len(shape)>8 or any(type(n) is not int or not 0<=n<=10**9 for n in shape)
                    or dtype not in ('F64','F32','F16','BF16','I64','I32','I16','I8','U8','BOOL','F8_E4M3','F8_E5M2')
                    or not isinstance(offset,list) or len(offset)!=2 or any(type(x) is not int for x in offset)
                    or not 0<=offset[0]<=offset[1]<=meta.st_size-8-size):raise ValueError('HEADER')
            shapes.append((name,shape,dtype));dtypes[dtype]=dtypes.get(dtype,0)+1
            elements+=math.prod(shape)
        result.update(state='HEADER_OBSERVED',tensors=len(shapes),elements=elements,dtypes=dtypes,
                      target_shapes_sha256=hashlib.sha256(json.dumps(sorted(shapes),separators=(',',':')).encode()).hexdigest())
    except (OSError,ValueError,UnicodeError,struct.error,TypeError):result['reason']='HEADER_UNVERIFIED'
    return result


def hf_config(path):
    try:
        doc,_,digest=document(path)
        data=selected(doc,('model_type','architectures','hidden_size','intermediate_size',
            'num_hidden_layers','num_attention_heads','num_key_value_heads','vocab_size',
            'num_experts','num_local_experts','num_experts_per_tok','torch_dtype','dtype','tie_word_embeddings'))
        if not data:return None
        weights=[]
        for file in sorted(path.parent.glob('*.safetensors'))[:80]:
            if file.is_file() and not file.is_symlink():weights.append({'name':file.name,'bytes':file.stat().st_size})
        return {'path':str(path.parent),'config_sha256':digest,'config':data,'shards':weights,
                'full_tensor_hash_verified':False}
    except (OSError,ValueError,UnicodeError):return None


def checkpoint(path):
    doc=optional_json(path/'trainer_state.json',3*SMALL)
    if not isinstance(doc,dict):return None
    step=doc.get('global_step')
    row={'path':str(path),'global_step':step if type(step) is int else None,
         'positive_step_recorded':type(step) is int and step>0,
         'training_provenance':'UNVERIFIED_TRAINER_STATE_ONLY','large_file_hashes_recomputed':False}
    row['artifacts']={name:file_record(path/name,hash_small=True) for name in CHECKPOINT_FILES}
    complete=all(item.get('present') and item.get('bytes',0)>0 and not item.get('symlink') for item in row['artifacts'].values())
    row['seven_recovery_artifacts_present']=complete
    row['checkpoint_name_matches_step']=path.name==f'checkpoint-{step}'
    row['trainer_summary']=selected(doc,('epoch','max_steps','num_train_epochs','best_metric'))
    history=doc.get('log_history')
    if isinstance(history,list):
        row['recent_numeric_training_metrics']=[selected(item,('step','loss','learning_rate','grad_norm','epoch'))
                                                for item in history[-5:] if isinstance(item,dict)]
    config=optional_json(path/'adapter_config.json')
    row['adapter_config']=selected(config,('base_model_name_or_path','peft_type','task_type','r',
        'lora_alpha','lora_dropout','target_modules','inference_mode','revision'))
    if (path/'adapter_model.safetensors').is_file():row['adapter_header']=tensor_header(path/'adapter_model.safetensors')
    lineage=optional_json(path.parent/'owner_lineage.json')
    if isinstance(lineage,dict):
        row['lineage_sha256']=hashlib.sha256(json.dumps(lineage,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        base=lineage.get('base') or {}
        row['lineage_base']=selected(base,('path','full_base_tensor_sha_verified'))
        metadata=base.get('metadata_sha256') if isinstance(base,dict) else None
        if isinstance(metadata,dict):row['lineage_base']['metadata_sha256']={k:v for k,v in metadata.items() if k in ('config.json','tokenizer_config.json','tokenizer.json','model.safetensors.index.json') and isinstance(v,str) and SHA.fullmatch(v)}
        row['lineage_targets']=selected(lineage.get('targets'),('target_schema_sha256','trainable_tensors','trainable_parameters','trainable_dtype'))
        row['lineage_training_config']=selected(lineage.get('training_config'),('max_steps','planned_steps','optimizer','precision','adapter_parameter_dtype','amp_scaler_state_required','seed'))
    receipt_path=path.parent/f'owner_receipt_step_{step}.json'
    receipt=optional_json(receipt_path)
    if isinstance(receipt,dict):
        row['receipt']=selected(receipt,('schema','native_sha256','lineage_sha256','start_step','global_step',
            'successful_optimizer_steps','skipped_optimizer_steps','loss','before_tensor_sha256','after_tensor_sha256',
            'adapter_delta_verified','merged','live_promoted','external_restore_verified'))
        recorded=receipt.get('checkpoint') or {};digests=recorded.get('files_sha256') if isinstance(recorded,dict) else None
        full_hash_record=bool(isinstance(digests,dict) and all(isinstance(digests.get(name),str) and SHA.fullmatch(digests[name]) for name in CHECKPOINT_FILES))
        matching_small=full_hash_record and all(not info.get('sha256') or info['sha256']==digests[name]
                                               for name,info in row['artifacts'].items())
        loss=number(receipt.get('loss'))
        structural=(type(step) is int and step>0 and
                    receipt.get('schema')=='NOX_T866U_FP32_ADAPTER_CONTINUATION_V1' and
                    receipt.get('global_step')==step and recorded.get('global_step')==step and
                    recorded.get('path')==str(path) and type(receipt.get('successful_optimizer_steps')) is int and
                    receipt['successful_optimizer_steps']>0 and loss is not None and
                    receipt.get('adapter_delta_verified') is True and
                    isinstance(receipt.get('before_tensor_sha256'),str) and SHA.fullmatch(receipt['before_tensor_sha256']) and
                    isinstance(receipt.get('after_tensor_sha256'),str) and SHA.fullmatch(receipt['after_tensor_sha256']) and
                    receipt['before_tensor_sha256']!=receipt['after_tensor_sha256'] and
                    receipt.get('lineage_sha256')==row.get('lineage_sha256'))
        row['receipt_complete_hash_record']=full_hash_record
        row['current_small_file_hashes_match_receipt']=bool(matching_small)
        row['training_provenance']='RECORDED_OPTIMIZER_DELTA_WITH_SMALL_FILE_READBACK' if complete and structural and matching_small else 'RECEIPT_PRESENT_NOT_VALIDATED'
    return row


def training_inventory():
    roots=[ROOT/'lora',ROOT/'progress_pull_t784u',ROOT/'ckpt',ROOT/'checkpoints',ROOT/'models']
    for path in list(ROOT.iterdir())[:500]:
        if path.is_dir() and not path.is_symlink() and re.match(r'^(?:progress_pull|train|runs|adapters|weights|ckpt|checkpoints)',path.name) and path not in roots:
            roots.append(path)
            if len(roots)>=30:break
    files,coverage=walk(roots,max_files=9000,max_dirs=1200,seconds=7)
    states=[p for p in files if p.name=='trainer_state.json']
    states.sort(key=lambda path:('runs_owner_hybrid' not in str(path),str(path.parent)))
    coverage['checkpoint_limit']=70;coverage['checkpoint_candidates_found']=len(states)
    coverage['checkpoint_scan_truncated']=len(states)>70
    checkpoints=[]
    for path in states[:70]:
        result=checkpoint(path.parent)
        if result:checkpoints.append(result)
    bases=[]
    for path in [p for p in files if p.name=='config.json'][:65]:
        result=hf_config(path)
        if result and result['shards']:bases.append(result)
    loose=[]
    for path in [p for p in files if p.name=='adapter_config.json' and p.parent/'trainer_state.json' not in states][:40]:
        config=optional_json(path)
        loose.append({'path':str(path.parent),'config':selected(config,('base_model_name_or_path','peft_type','r','target_modules')),
                      'adapter':file_record(path.parent/'adapter_model.safetensors'),
                      'training_provenance':'UNKNOWN_NO_TRAINER_STATE'})
    reports=[]
    for path in files:
        if len(reports)>=35:break
        if not path.name.endswith('.json') or not re.search(r'(merge|quant|export|provenance|promotion|manifest)',path.name,re.I):continue
        doc=optional_json(path)
        values=selected(doc,('schema','base_model','base_path','adapter_path','checkpoint','checkpoint_path',
            'gguf_path','output_path','input_sha256','output_sha256','sha256','global_step','merged','verified','live_promoted'))
        if values:reports.append({'path':str(path),'recorded_fields':values,'evidence':'UNVERIFIED_PROVENANCE_RECORD'})
    grouped={}
    for row in checkpoints:
        if not row['positive_step_recorded']:continue
        identity=row.get('lineage_sha256') or str(Path(row['path']).parent)
        previous=grouped.get(identity)
        if previous is None or row['global_step']>previous['global_step']:
            grouped[identity]={'lineage':identity,'path':row['path'],'global_step':row['global_step'],
                               'training_provenance':row['training_provenance']}
    flags={name:(ROOT/name).exists() for name in ('state/TRAIN_HOLD.flag','state/TRAIN_PAUSE_REQUEST.flag',
                                               'state/train_wants_gpu1','STOP','STOP.flag')}
    heartbeat=[]
    for name in ('train_volta_t866u.json','train_volta_wrapper_t866u.json','owner_hybrid_training.json'):
        path=ROOT/'status'/name
        try:
            doc,meta,_=document(path)
            heartbeat.append({'path':str(path),'age_seconds':max(0,time.time()-meta.st_mtime),
                'fields':selected(doc,('phase','step','global_step','max_steps','loss','successful_optimizer_steps',
                                      'skipped_optimizer_steps','trainable_dtype','output','method')),
                'error_present':isinstance(doc,dict) and bool(doc.get('error'))})
        except (OSError,ValueError,UnicodeError):pass
    return {'state':'OBSERVED','coverage':coverage,'flags':flags,'heartbeat':heartbeat,'hf_bases':bases,
            'checkpoints':checkpoints,'adapters_without_trainer_state':loose,'provenance_records':reports,
            'highest_recorded_step_per_lineage':list(grouped.values()),
            'recency_policy':'NO_CROSS_LINEAGE_OR_MTIME_PROMOTION; RECORDED_STEP_IS_NOT_CURRENT_TENSOR_PROOF',
            'all_progress_merged':'UNKNOWN_REQUIRES_EXACT_TRAINED_ADAPTER_TO_ACTIVE_GGUF_EXPORT_CHAIN',
            'source_memory_and_weight_updates_are_distinct':True}


def installed_packages():
    environments={}
    normalized={name.replace('-','_').lower():name for name in PACKAGE_NAMES}
    for root in (Path('/root/venv_volta'),ROOT/'venv',ROOT/'media/venv'):
        found={}
        for site in list(root.glob('lib/python*/site-packages'))[:3]:
            for folder in list(site.glob('*.dist-info'))[:1800]:
                stem=folder.name.rsplit('.dist-info',1)[0].rsplit('-',1)[0].replace('-','_').lower()
                if stem not in normalized:continue
                try:
                    # Distribution headers only. Never import Torch or native .pth.
                    with (folder/'METADATA').open('rb') as file:header=file.read(20000).decode(errors='replace')
                    match=re.search(r'^Version:\s*(\S{1,80})',header,re.M)
                    if match and re.fullmatch(r'[A-Za-z0-9_.+!-]+',match[1]):found[normalized[stem]]=match[1]
                except OSError:continue
        environments[str(root)]={'present':root.is_dir(),'versions':found,'runtime_import_tested':False}
    return environments


def source_file(path):
    try:
        raw,meta=bounded(path,750000);tree=ast.parse(raw)
        imports=set();calls=set();routes=set();empty=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.update(alias.name for alias in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:imports.add(node.module)
            elif isinstance(node,ast.Call):
                fn=node.func
                if isinstance(fn,ast.Name):name=fn.id
                elif isinstance(fn,ast.Attribute):name=fn.attr
                else:continue
                if name.startswith(('register_','install')):calls.add(name)
                if name in ('get','post','put','delete','patch','mount') and node.args and isinstance(node.args[0],ast.Constant):
                    value=node.args[0].value
                    if isinstance(value,str) and value.startswith(('/api/','/nox/','/chat','/nox-web-')) and len(value)<150:routes.add(value)
            elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in ('emotion_addendum','extra_context','pre_answer_context'):
                body=[item for item in node.body if not isinstance(item,ast.Expr)]
                if len(body)==1 and isinstance(body[0],ast.Return) and isinstance(body[0].value,ast.Constant) and body[0].value.value in ('',None):empty.append(node.name)
        return {'path':str(path),'bytes':meta.st_size,'sha256':hashlib.sha256(raw).hexdigest(),
                'syntax':'PARSED','imports':sorted(imports)[:100],'registration_calls_declared':sorted(calls)[:35],
                'route_declarations':sorted(routes)[:70],'hooks_returning_empty':empty,
                'runtime_execution':'UNKNOWN_SOURCE_IMPORTS_DO_NOT_PROVE_EXECUTION'}
    except FileNotFoundError:return {'path':str(path),'syntax':'MISSING'}
    except (OSError,ValueError,SyntaxError,UnicodeError):return {'path':str(path),'syntax':'UNVERIFIED'}


def wiring_inventory():
    paths=[ROOT/'scripts'/(name+'.py') for name in SOURCE_NAMES]
    paths.extend((ROOT/'s03_memory.py',ROOT/'understanding/hook.py',ROOT/'ops/ops_agent.py',ROOT/'program/selfops/nox_selfops.py'))
    rows=[source_file(path) for path in paths]
    known={Path(row['path']).stem:row for row in rows}
    # Add direct local dependencies only, bounded and never executed.
    additional=[]
    for row in rows:
        for name in row.get('imports',[]):
            base=name.split('.')[0]
            if base in known or not re.fullmatch(r'(?:nox|s03|emotion|memory|brain|genesis|reflection|helper)\w{0,80}',base):continue
            for folder in (ROOT/'scripts',ROOT,ROOT/'program',ROOT/'understanding'):
                path=folder/(base+'.py')
                if path.is_file() and not path.is_symlink():
                    value=source_file(path);additional.append(value);known[base]=value;break
            if len(additional)>=30:break
        if len(additional)>=30:break
    rows+=additional
    graph=[]
    for row in rows:
        for name in row.get('imports',[]):
            if name.split('.')[0] in known:
                graph.append({'from':Path(row['path']).stem,'to':name,
                              'target_present':known[name.split('.')[0]].get('syntax')=='PARSED'})
    excerpts=[]
    for name,functions in (
        (ROOT/'scripts/nox_agent_pool_t858u.py',('prepare_payload','fixed_prefix','try_deterministic')),
        (ROOT/'understanding/hook.py',('handle_owner_chat',)),
        (ROOT/'scripts/nox_tools.py',('heuristic_tools','dispatch','parse_tool_calls'))):
        excerpts.append(diagnostic_source(name,functions))
    excerpts.append(implementation_source(ROOT/'s03_memory.py'))
    return {'state':'OBSERVED','packages':installed_packages(),'sources':rows,'local_import_edges':graph[:180],
            'targeted_wrapper_diagnostics':excerpts,
            'source_only_gaps':[{'module':Path(row['path']).stem,'reason':'EMPTY_'+hook.upper()}
                                for row in rows for hook in row.get('hooks_returning_empty',[])],
            'runtime_registration_proof':'UNKNOWN_UNLESS_MATCHING_NATIVE_ACCEPTANCE_RECEIPT_EXISTS',
            'native_modules_imported_by_probe':False}


def downloads_inventory():
    result={'state':'OBSERVED','manifests':[],'partial_files':[],'assets':[]}
    versions=installed_packages().get('/root/venv_volta',{}).get('versions',{})
    manifest=ROOT/'config/owner_download_manifest.json'
    try:
        doc,meta,digest=document(manifest,2*SMALL)
        components=[]
        for item in (doc.get('components') or [])[:100]:
            if not isinstance(item,dict):continue
            row=selected(item,('id','name','package','state','decision','owner_executor','installed_version'))
            if item.get('package') in PACKAGE_NAMES:
                current=versions.get(item['package']);row['currently_installed_version']=current
                row['version_matches_manifest']=current==item.get('installed_version') if item.get('installed_version') else None
            components.append(row)
        result['manifests'].append({'path':str(manifest),'sha256':digest,'age_seconds':max(0,time.time()-meta.st_mtime),
                                     'components':components,'scope':'CLAIMED_PLAN_RECONCILED_WITH_CURRENT_PACKAGE_METADATA'})
    except (OSError,ValueError,UnicodeError,AttributeError):result['manifest_state']='UNKNOWN'
    media=ROOT/'config/owner_media_runtime.json'
    doc=optional_json(media)
    if isinstance(doc,dict):
        result['media_enabled']=doc.get('enabled') is True
        for item in (doc.get('assets') or [])[:24]:
            if not isinstance(item,dict):continue
            location=item.get('path')
            if not isinstance(location,str) or allowed_model_path(location) is None:
                result['assets'].append({'filename':label(item.get('filename')),'state':'MISSING_OR_UNTRUSTED_PATH'});continue
            actual=file_record(location,hash_small=True)
            actual.update(selected(item,('kind','role','filename','revision','license')))
            actual['expected_bytes']=number(item.get('bytes'))
            expected=item.get('sha256');actual['expected_sha256']=expected if isinstance(expected,str) and SHA.fullmatch(expected) else None
            match=actual.get('bytes')==item.get('bytes') and actual.get('mtime_ns')==item.get('stat_mtime_ns')
            actual['prior_verification_metadata_still_matches']=bool(item.get('verified') is True and match)
            actual['current_large_sha_verified']=False
            result['assets'].append(actual)
    roots=(ROOT/'models',ROOT/'lora',ROOT/'downloads',ROOT/'progress_pull_t784u',ROOT/'media',Path('/dev/shm/nox_media'))
    files,coverage=walk(roots,max_files=7000,max_dirs=900,seconds=5)
    for path in files:
        if len(result['partial_files'])>=70:break
        if path.name.endswith(('.part','.partial','.incomplete','.download')):
            result['partial_files'].append(file_record(path))
    checksums=[]
    for path in files:
        if len(checksums)>=40:break
        if path.suffix.lower() not in ('.sha','.sha256'):continue
        try:
            raw,_=bounded(path,8192)
            matches=re.findall(r'\b[a-fA-F0-9]{64}\b',raw.decode(errors='replace'))
            if matches:checksums.append({'path':str(path),'recorded_sha256':[value.lower() for value in matches[:8]],
                                        'current_large_file_hash_verified':False})
        except (OSError,ValueError):pass
    statuses=[]
    for path in sorted((ROOT/'status').glob('*download*.json'))[:25]:
        try:
            doc,meta,_=document(path)
            statuses.append({'path':str(path),'age_seconds':max(0,time.time()-meta.st_mtime),
                            'fields':selected(doc,('state','status','phase','running','paused','active','done',
                                                  'bytes','bytes_done','bytes_total','completed','failed','workers'))})
        except (OSError,ValueError,UnicodeError):pass
    result.update(coverage=coverage,checksum_records=checksums,download_statuses=statuses,
                  downloaded_vs_connected_rule='FILE_PRESENCE_OR_MANIFEST_STATE_IS_NOT_RUNTIME_BINDING')
    return result


def workers_snapshot():
    path=ROOT/'status/agents_t856u.json'
    result={'state':'UNKNOWN','workers':[]}
    try:
        doc,meta,digest=document(path,750000)
        rows=doc.get('workers');n=doc.get('n');age=time.time()-meta.st_mtime
        if type(n) is not int or not 1<=n<=64 or not isinstance(rows,list) or len(rows)!=n:raise ValueError('WORKERS_SHAPE')
        ids=set();claims=[];busy=0
        for row in rows:
            if not isinstance(row,dict):raise ValueError('WORKERS_SHAPE')
            name=row.get('id');state=row.get('status');task=row.get('current_task')
            if not isinstance(name,str) or not re.fullmatch(r'nox-agent-\d{2,3}',name) or name in ids:raise ValueError('WORKERS_ID')
            ids.add(name);out={'id':name,'status':state}
            if state=='busy' and isinstance(task,dict) and isinstance(task.get('id'),str) and task['id']:
                claim=hashlib.sha256(task['id'].encode()).hexdigest();claims.append(claim);busy+=1
                out['claim_id_sha256']=claim
                out['handler']=label(task.get('handler'))
            elif state!='idle' or task is not None:raise ValueError('WORKERS_STATE')
            result['workers'].append(out)
        result.update(state='OBSERVED' if 0<=age<=45 else 'STALE',configured=n,busy=busy,idle=n-busy,
                      claim_ids_unique=len(claims)==len(set(claims)),age_seconds=round(age,3),status_sha256=digest)
    except (OSError,ValueError,UnicodeError,AttributeError):result['state']='UNKNOWN'
    return result


def resources_inventory():
    owners=supervisor();processes=process_rows(owners)
    cgroup={}
    for name in ('cpu.max','memory.max','memory.current','memory.high','memory.events'):
        try:cgroup[name]=Path('/sys/fs/cgroup',name).read_text()[:2000].strip()
        except OSError:cgroup[name]=None
    quota=None
    try:
        amount,period=cgroup['cpu.max'].split()
        if amount!='max':quota=int(amount)/int(period)
    except (AttributeError,ValueError,ZeroDivisionError):pass
    memory={}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            match=re.fullmatch(r'(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+) kB',line)
            if match:memory[match[1]+'_bytes']=int(match[2])*1024
    except OSError:pass
    rc,output=command(['nvidia-smi','--query-gpu=index,uuid,name,memory.total,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'])
    gpus=[]
    for line in output.splitlines()[:16]:
        values=[value.strip() for value in line.split(',')]
        if len(values)!=7:continue
        try:gpus.append({'index':int(values[0]),'uuid':label(values[1]),'name':label(values[2]),
                         'total_mib':int(values[3]),'used_mib':int(values[4]),'free_mib':int(values[5]),'utilization_percent':int(values[6])})
        except ValueError:continue
    apps=[];app_rc,out=command(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader,nounits'])
    for line in out.splitlines()[:80]:
        values=[value.strip() for value in line.split(',')]
        if len(values)!=3 or not values[0].isdigit():continue
        reported=int(values[0]);matches=[row for row in processes if reported in [row['pid'],*row['namespace_pids']]]
        apps.append({'reported_pid':reported,'gpu_uuid':label(values[1]),
                     'used_mib':int(values[2]) if values[2].isdigit() else None,
                     'local_pid':matches[0]['pid'] if len(matches)==1 else None,
                     'ownership':matches[0]['supervisor_owner'] if len(matches)==1 else 'UNKNOWN'})
    disks={str(path):dict(zip(('total_bytes','used_bytes','free_bytes'),shutil.disk_usage(path)))
           for path in (ROOT,Path('/dev/shm')) if path.exists()}
    config=optional_json(ROOT/'config/dispatcher_agents_t868u.json')
    return {'state':'OBSERVED','cpu_affinity_count':len(os.sched_getaffinity(0)),'cpu_quota_cores':quota,
            'cgroup':cgroup,'host_memory':memory,'disk':disks,'gpu_query_rc':rc,'gpus':gpus,
            'gpu_apps_query_rc':app_rc,'gpu_apps':apps,'services':owners,'processes':processes,
            'workers':workers_snapshot(),'worker_configuration':selected(config,('workers','min_workers','max_workers','tuner_may_adjust')),
            'boost_policy':selected(optional_json(ROOT/'state/task_boost_mode.json'),('schema','enabled','mode','training_allowed','training_service'))}


def redact_source(text):
    text=re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----','[PRIVATE_KEY_REDACTED]',text)
    text=re.sub(r'(?:hf_|ghp_|github_pat_|sk-(?:proj-)?)[A-Za-z0-9_-]{12,}','[TOKEN_REDACTED]',text)
    text=re.sub(r'(?i)Bearer\s+[^\s"\']+','Bearer [REDACTED]',text)
    text=re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@',r'\1[REDACTED]@',text)
    text=re.sub(r'''(?i)(["']?\b_*(?:[A-Za-z][A-Za-z0-9]*_)*(?:password|passwd|secret|api[_-]?key|access[_-]?key|authorization|(?:refresh|access|auth|hf|openai|bearer|x)[_-]?token|token)["']?\s*[:=]\s*)(["'])[^\n]*?\2''',r'\1"[REDACTED_VALUE]"',text)
    text=re.sub(r'(?im)^([^\n]*\b(?:password|secret|api_key|access_key|authorization|refresh_token|access_token)\b\s*[:=])[^\n]+',r'\1 [REDACTED_VALUE]',text)
    return text


def diagnostic_source(path,functions):
    """Explicitly requested wrapper excerpts, never chat logs or environment."""
    result={'path':str(path),'functions':[],'referenced_constants':[]}
    try:
        raw,_=bounded(path,750000);source=raw.decode('utf-8');tree=ast.parse(source)
        result['sha256']=hashlib.sha256(raw).hexdigest();remaining=20000;referenced=set()
        for node in tree.body:
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in functions:continue
            referenced.update(item.id for item in ast.walk(node) if isinstance(item,ast.Name))
            excerpt=ast.get_source_segment(source,node) or ''
            safe=redact_source(excerpt);part=safe.encode()[:min(remaining,7000)].decode(errors='ignore');remaining-=len(part.encode())
            result['functions'].append({'name':node.name,'line':node.lineno,'source':part,
                                        'redacted':safe!=excerpt,'truncated':part!=safe})
        for node in tree.body:
            if remaining<=0:break
            if not isinstance(node,ast.Assign) or len(node.targets)!=1 or not isinstance(node.targets[0],ast.Name):continue
            name=node.targets[0].id
            if name not in referenced or not name.isupper():continue
            if re.search(r'KEY|SECRET|TOKEN|PASSWORD|COOKIE|AUTH|SESSION',name):
                result['referenced_constants'].append({'name':name,'value':'REDACTED'});continue
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            if not isinstance(value,(str,int,float,bool,list,tuple,dict,set)):continue
            excerpt=ast.get_source_segment(source,node) or ''
            safe=redact_source(excerpt);part=safe.encode()[:min(remaining,4000)].decode(errors='ignore');remaining-=len(part.encode())
            result['referenced_constants'].append({'name':name,'source':part,'redacted':safe!=excerpt,'truncated':part!=safe})
    except FileNotFoundError:result['state']='MISSING'
    except (OSError,ValueError,SyntaxError,UnicodeError):result['state']='UNVERIFIED'
    else:result['state']='BOUNDED_SOURCE_EXCERPTS'
    return result


def implementation_source(path):
    result={'path':str(path),'state':'UNKNOWN'}
    try:
        raw,_=bounded(path,750000);text=raw.decode();tree=ast.parse(text)
        safe=redact_source(text);part=safe.encode()[:30000].decode(errors='ignore')
        result.update(state='BOUNDED_SOURCE_EXCERPT',sha256=hashlib.sha256(raw).hexdigest(),
                      source=part,source_redacted=safe!=text,source_truncated=part!=safe,
                      function_names=[node.name for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))][:100])
    except FileNotFoundError:result['state']='MISSING'
    except (OSError,ValueError,SyntaxError,UnicodeError):result['state']='UNVERIFIED'
    return result


def literal_paths(path):
    """Extract literal SQLite locations without executing the memory module."""
    result=[]
    try:
        raw,_=bounded(path,750000);tree=ast.parse(raw)
        for node in ast.walk(tree):
            if not isinstance(node,ast.Constant) or not isinstance(node.value,str):continue
            value=node.value
            if len(value)<300 and value.endswith(('.db','.sqlite','.sqlite3')):
                candidate=Path(value)
                if candidate.is_absolute() and candidate.is_relative_to(ROOT):result.append(candidate)
    except (OSError,ValueError,SyntaxError,UnicodeError):pass
    return result


def memory_database(path):
    row={'path':str(path),'state':'UNKNOWN','content_exported':False}
    if path.is_symlink() or not path.is_file():return row
    deadline=time.monotonic()+2.5
    db=None
    try:
        uri='file:'+urllib.parse.quote(str(path),safe='/')+'?mode=ro'
        db=sqlite3.connect(uri,uri=True,timeout=.5)
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA busy_timeout=500')
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        tables={record[0] for record in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 's03_items' not in tables:return dict(row,state='OTHER_SQLITE_SCHEMA')
        schema={};counts={}
        for name in ('s03_items','s03_sources','s03_links','nox_v29_dialogs','nox_v29_dialog_messages'):
            if name not in tables:continue
            schema[name]=[{'column':record[1],'type':record[2]} for record in db.execute('PRAGMA table_info('+name+')')][:60]
            try:counts[name]=db.execute('SELECT count(*) FROM '+name).fetchone()[0]
            except sqlite3.Error:counts[name]=None
        check=None
        if time.monotonic()<deadline:
            try:check=db.execute('PRAGMA quick_check(1)').fetchone()[0]=='ok'
            except sqlite3.Error:pass
        row.update(state='S03_SCHEMA_OBSERVED',bytes=path.stat().st_size,schema=schema,counts=counts,
                   quick_check_ok=check,query_budget_seconds=2.5,
                   semantic_recall_quality='UNKNOWN_NOT_A_CONTENT_QUERY')
    except (OSError,sqlite3.Error):row['reason']='BOUNDED_SQLITE_READ_UNAVAILABLE'
    finally:
        if db is not None:db.close()
    return row


def senior_configuration():
    result=[]
    for name in ('senior_model.json','dispatcher_mentor.json'):
        path=ROOT/'config'/name;doc=optional_json(path,100000)
        row={'config_name':name,'present':isinstance(doc,dict)}
        if isinstance(doc,dict):
            parsed=urllib.parse.urlparse(doc.get('base_url') or '') if isinstance(doc.get('base_url'),str) else None
            key=doc.get('api_key_env');key_name_valid=isinstance(key,str) and re.fullmatch('[A-Z][A-Z0-9_]{2,100}',key) is not None
            row.update(enabled=doc.get('enabled') is True,senior_role=doc.get('role')=='senior',
                       model_configured=isinstance(doc.get('model'),str) and bool(doc['model']),
                       endpoint_configured=bool(parsed and parsed.hostname),
                       endpoint_has_embedded_credentials=bool(parsed and (parsed.username or parsed.password or parsed.query)),
                       endpoint_loopback=bool(parsed and parsed.hostname in ('localhost','127.0.0.1','::1')),
                       credential_reference_configured=key_name_valid,
                       credential_available_to_probe=bool(key_name_valid and os.environ.get(key)),
                       actual_senior_request_verified=False)
        result.append(row)
    return result


def credential_presence():
    """Exact provider booleans only, from identified NOX processes/configuration."""
    result={'process_environments':[],'configuration_files':[],'values_exported':False,
            'credential_validity_or_network_access_verified':False}
    owners=supervisor()
    for row in process_rows(owners):
        if row.get('supervisor_owner') not in ('nox-proxy','nox-dispatcher-t855u'):continue
        path=PROC/str(row['pid'])
        try:
            current=int((path/'stat').read_text().rsplit(') ',1)[1].split()[19])
            if current!=row['start_ticks']:continue
            with (path/'environ').open('rb') as file:raw=file.read(100001)
            complete=len(raw)<=100000;raw=raw[:100000]
            if int((path/'stat').read_text().rsplit(') ',1)[1].split()[19])!=current:continue
            values={name:False for name in CREDENTIAL_NAMES}
            for field in raw.split(b'\0'):
                key,_,value=field.partition(b'=')
                if key in tuple(name.encode() for name in CREDENTIAL_NAMES):values[key.decode()]=bool(value.strip())
            result['process_environments'].append({'service':row['supervisor_owner'],'pid':row['pid'],
                                                  'start_ticks':row['start_ticks'],'read_complete':complete,'nonempty':values})
        except (OSError,ValueError,IndexError):continue
    paths=[ROOT/'.env',ROOT/'config/.env']
    for path in sorted((ROOT/'config').iterdir())[:180] if (ROOT/'config').is_dir() else []:
        if path.suffix in ('.json','.env') and re.search(r'api|provider|model|senior|mentor|brain|gateway|settings|config|secret|credentials',path.name,re.I):paths.append(path)
    for path in paths[:60]:
        try:raw,_=bounded(path,200000)
        except (OSError,ValueError):continue
        present={name:False for name in CREDENTIAL_NAMES};references=dict(present)
        if path.suffix=='.json':
            try:doc=json.loads(raw)
            except (ValueError,UnicodeError):continue
            def scan(value,parent='',depth=0):
                if depth>7:return
                if isinstance(value,dict):
                    for key,item in list(value.items())[:150]:
                        upper=str(key).upper()
                        if upper in present and isinstance(item,str):present[upper]=bool(item.strip())
                        if key in ('api_key_env','key_env') and item in CREDENTIAL_NAMES:references[item]=True
                        provider=parent+' '+str(key)+' '+str(value.get('provider',''))
                        if str(key).lower() in ('api_key','api-key','key') and isinstance(item,str) and item.strip():
                            for token,names in (('openai',('OPENAI_API_KEY',)),('anthropic',('ANTHROPIC_API_KEY',)),
                                                ('gemini',('GEMINI_API_KEY',)),('google',('GOOGLE_API_KEY',))):
                                if token in provider.casefold():
                                    for name in names:present[name]=True
                        if isinstance(item,(dict,list)):scan(item,provider,depth+1)
                elif isinstance(value,list):
                    for item in value[:50]:scan(item,parent,depth+1)
            scan(doc)
        else:
            for line in raw.decode(errors='replace').splitlines():
                match=re.match(r'^\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*$',line)
                if match and match[1] in present:present[match[1]]=bool(match[2].strip().strip('"\''))
        if any(present.values()) or any(references.values()):
            result['configuration_files'].append({'path':str(path),'nonempty':present,'env_reference':references})
    return result


def acceptance_receipts():
    rows=[]
    paths=sorted((ROOT/'state').glob('owner_chat_upgrade_*.json'),key=lambda p:p.name)[-5:]
    for path in paths:
        doc=optional_json(path,4*SMALL)
        if not isinstance(doc,dict):continue
        summary=selected(doc,('schema','request','source_sha','state','started','finished','chat_restarted',
                              'model_restarted','performance_targets_passed','rollback_verified'))
        tests=[]
        for item in doc.get('acceptance',[])[:30]:
            if not isinstance(item,dict) or item.get('kind') not in ('chat_synthetic_latency','chat_history_followup',
                                                                  'chat_before_probe','chat_executor_question'):continue
            data=item.get('data') or {}
            tests.append({'kind':item['kind'],'evidence':selected(data,('saved_verified','arithmetic_pass','history_model_pass',
                'nonloopback_peer','owner_status_bound','owner_executors_access','verified_six_plus_nox',
                'performance_target_pass','total_ms','stream_total_ms'))})
        rows.append({'path':str(path),'summary':summary,'acceptance_booleans_and_timing':tests,
                     'private_or_public_prompt_text_exported':False})
    return rows


def memory_and_integrations():
    files,coverage=walk((ROOT/'memory',ROOT/'kb'),max_files=1800,max_dirs=200,seconds=3)
    paths={p for p in files if p.suffix in ('.db','.sqlite','.sqlite3')}
    paths.update(literal_paths(ROOT/'scripts/s03_memory.py'))
    paths.update(literal_paths(ROOT/'s03_memory.py'))
    databases=[memory_database(path) for path in sorted(paths)[:12]]
    code,data,elapsed=local_json(8080,'/nox/s03/status')
    allowed_counts=('items','sources','links','concepts','rows','messages','dialogs','memories','chunks','facts')
    counts=selected(data.get('counts'),allowed_counts) if isinstance(data,dict) else {}
    health={}
    for port in (8080,8082,8188):
        status,_,duration=local_json(port,'/health',timeout=2)
        health[str(port)]={'http':status,'seconds':duration}
    storage={}
    for name in ('cold_drive.conf','cold_pc.conf'):
        path=ROOT/'state'/name
        storage[name]={'present':path.is_file() and not path.is_symlink(),
                       'mode_0600':path.is_file() and not path.is_symlink() and stat.S_IMODE(path.stat().st_mode)==0o600}
    return {'state':'OBSERVED','database_coverage':coverage,'databases':databases,
            's03_status':{'http':code,'seconds':elapsed,'counts':counts},'health':health,
            'senior_api':senior_configuration(),'senior_credentials':credential_presence(),'storage_config_booleans':storage,
            'recent_owner_chat_acceptance':acceptance_receipts(),
            'memory_record_text_selected_or_exported':False,'optimizer_or_tensor_updates_tested':False}


PROBES=(('active_model',active_model),('training',training_inventory),('downloads',downloads_inventory),
        ('wiring',wiring_inventory),('resources',resources_inventory),('memory_integrations',memory_and_integrations))


def probe(name,function):
    started=time.time()
    try:
        value=function()
        return {'domain':name,'started_at':started,'finished_at':time.time(),'result':value}
    except Exception as error:
        return {'domain':name,'started_at':started,'finished_at':time.time(),
                'result':{'state':'UNKNOWN','error_type':type(error).__name__}}


def gap_map(results):
    domains={item['domain']:item['result'] for item in results};gaps=[]
    for name,data in domains.items():
        if data.get('state')=='UNKNOWN':gaps.append({'domain':name,'code':'BOUNDED_PROBE_UNVERIFIED','state':'UNKNOWN'})
    active=domains.get('active_model',{});servers=active.get('model_processes') or []
    if not servers or any(row.get('loaded_identity_evidence')!='MAPPED_INODE_MATCH' for row in servers):
        gaps.append({'domain':'active_model','code':'ACTIVE_LOADED_WEIGHT_INODE_UNVERIFIED','state':'UNKNOWN'})
    checkpoints=domains.get('training',{}).get('checkpoints') or []
    if not any(row.get('positive_step_recorded') for row in checkpoints):
        gaps.append({'domain':'training','code':'NO_POSITIVE_OPTIMIZER_STEP_OBSERVED','state':'NOT_OBSERVED'})
    gaps.append({'domain':'training','code':'EXACT_ADAPTER_MERGE_EXPORT_TO_LIVE_GGUF_CHAIN_UNVERIFIED','state':'UNKNOWN'})
    for item in domains.get('wiring',{}).get('source_only_gaps',[]):
        gaps.append({'domain':'wiring','code':item['reason'],'module':item['module'],'state':'SOURCE_OBSERVED'})
    workers=domains.get('resources',{}).get('workers') or {}
    if workers.get('state')!='OBSERVED' or workers.get('configured')!=6 or workers.get('claim_ids_unique') is not True:
        gaps.append({'domain':'resources','code':'SIX_FRESH_UNIQUE_EXECUTORS_UNVERIFIED','state':'UNKNOWN'})
    media=domains.get('downloads',{})
    if media.get('media_enabled') is not True or not media.get('assets'):
        gaps.append({'domain':'downloads','code':'IMAGE_VIDEO_RUNTIME_NOT_READY','state':'NOT_OBSERVED'})
    memory=domains.get('memory_integrations',{})
    if not any(row.get('state')=='S03_SCHEMA_OBSERVED' for row in memory.get('databases',[])):
        gaps.append({'domain':'memory_integrations','code':'S03_DATABASE_SCHEMA_UNVERIFIED','state':'UNKNOWN'})
    if not any(row.get('enabled') and row.get('senior_role') and row.get('endpoint_configured') and
               row.get('model_configured') for row in memory.get('senior_api',[])):
        gaps.append({'domain':'memory_integrations','code':'SENIOR_API_CONFIGURATION_NOT_OBSERVED','state':'UNKNOWN'})
    return gaps


def write_receipt(path,value):
    if path.exists() or path.is_symlink() or path.parent.is_symlink() or not path.parent.is_dir():
        raise RuntimeError('HOLD_INVENTORY_RECEIPT_PATH')
    fd,name=tempfile.mkstemp(prefix='.owner-inventory-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as file:
            json.dump(value,file,ensure_ascii=False,allow_nan=False,separators=(',',':'))
            file.write('\n');file.flush();os.fsync(file.fileno())
        # No overwriting a prior owner receipt, even across concurrent invocations.
        os.link(name,path,follow_symlinks=False)
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(parent)
        finally:os.close(parent)
    finally:
        if os.path.exists(name):os.unlink(name)


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or len(request)>24 or not re.fullmatch('[a-f0-9]{40}',source):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    started=time.time();results=[]
    with ThreadPoolExecutor(max_workers=6,thread_name_prefix='nox-read-inventory') as pool:
        futures=[pool.submit(probe,name,function) for name,function in PROBES]
        for future in as_completed(futures):
            item=future.result();results.append(item)
            if item['domain']=='wiring':
                excerpts=item['result'].get('targeted_wrapper_diagnostics') or []
                for excerpt in excerpts:emit('full_inventory_source_excerpt',excerpt)
                public=dict(item,result=dict(item['result'],targeted_wrapper_diagnostics=[
                    {k:v for k,v in excerpt.items() if k in ('path','state','sha256')}
                    for excerpt in excerpts]))
                emit('full_inventory_domain',public)
            else:emit('full_inventory_domain',item)
    gaps=gap_map(results)
    receipt={'schema':SCHEMA,'instructions_version':'0.0.6','instance_id':60509551,
             'request':request,'source_sha':source,'started_at':started,'finished_at':time.time(),
             'max_concurrent_read_probes':6,'domains':results,'gap_map':gaps,
             'native_services_modified':False,'weights_loaded_or_modified':False,'model_promoted':False,
             'files_deleted':0,'private_chat_or_environment_exported':False,
             'only_write':'PRIVATE_INVENTORY_RECEIPT'}
    path=ROOT/'state'/('owner_full_inventory_'+request+'.json');write_receipt(path,receipt)
    emit('full_inventory_summary',{'schema':SCHEMA,'receipt_path':str(path),'domains_completed':len(results),
                                  'seconds':round(time.time()-started,3),'gap_map':gaps,
                                  'weight_promotion_performed':False})
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error)
        emit('full_inventory_failed',{'reason':code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else type(error).__name__})
        raise SystemExit(1)
