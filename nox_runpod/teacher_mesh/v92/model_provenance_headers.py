"""V92: inspect only safetensors JSON headers and index manifests, no tensor bytes."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
prev=ssh.api
def settle(method,path,key,data=None):
    r=prev(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,os,hashlib,re,struct,collections
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V92_HEADER_SCHEMA=NOX_HF_TENSOR_HEADER_AND_CHECKPOINT_PROVENANCE_V1')
root=Path('/root/nox')
ids={'e646ed03a2d1992e':'large_hf','8a8b9faeefcbdfcb':'optimizer_pair'}
tracked={}
for parent,dirs,files in os.walk(root,followlinks=False):
    depth=len(Path(parent).relative_to(root).parts)
    dirs[:]=[d for d in dirs if d not in ('.git','.cache','venv','.venv','__pycache__','site-packages','logs','.ssh','node_modules') and not (Path(parent)/d).is_symlink()][:100]
    hint=hashlib.sha256(parent.encode()).hexdigest()[:16]
    if hint in ids:tracked[ids[hint]]=(Path(parent),files)
    if len(tracked)==len(ids):break
def safetensors_header(p):
    with p.open('rb') as f:
        header_len=struct.unpack('<Q',f.read(8))[0]
        if not 1<=header_len<=8_000_000:return None
        h=json.loads(f.read(header_len))
    if not isinstance(h,dict):return None
    names=[k for k,v in h.items() if k!='__metadata__' and isinstance(v,dict)]
    dtypes=collections.Counter()
    count=0;bytes_est=0
    for key in names:
        v=h[key]
        shape=v.get('shape')
        if isinstance(shape,list) and len(shape)<=8 and all(type(d) is int and d>=0 for d in shape):
            num=1
            for dim in shape:num*=dim
            count+=num
            dt=v.get('dtype')
            dtypes[str(dt)]+=1
        offs=v.get('data_offsets')
        if isinstance(offs,list) and len(offs)==2 and all(type(x) is int for x in offs):
            bytes_est+=max(0,offs[1]-offs[0])
    lora=sum('lora' in k.lower() or 'adapter' in k.lower() for k in names)
    is_expert=sum('expert' in k.lower() for k in names)
    return {'tensors':len(names),'num_elements':count,'dtypes':dict(dtypes),
            'payload_bytes':bytes_est,'lora_adapter_keys':lora,
            'expert_key_count':is_expert}
for kind,(dir,files) in tracked.items():
    config=dir/'config.json'
    manifest=next((dir/f for f in files if f.endswith('.safetensors.index.json')),None)
    basic={'kind':kind,'found':True,'safetensors_files':len([n for n in files if n.endswith('.safetensors')]),
           'config':config.is_file(),'index':bool(manifest),'optimizer_files':sum('optimizer' in n.lower() for n in files)}
    if config.is_file() and config.stat().st_size<600000:
        try:
            conf=json.loads(config.read_text())
            chosen=('model_type','hidden_size','num_hidden_layers','num_attention_heads',
                    'num_key_value_heads','num_experts','num_experts_per_tok','vocab_size')
            for k in chosen:
                v=conf.get(k)
                if type(v) in (int,str) and len(str(v))<=55:basic[k]=v
            arch=conf.get('architectures')
            if isinstance(arch,list):basic['architectures']=[str(x)[:75] for x in arch[:4]]
        except Exception:basic['config_parse']='HOLD'
    if manifest and manifest.stat().st_size<2_000_000:
        try:
            index=json.loads(manifest.read_text())
            weights=index.get('weight_map') or {}
            needed=set(weights.values())
            have=set(files)
            basic['indexed_tensors']=len(weights)
            basic['indexed_shards']=len(needed)
            basic['all_index_shards_present']=needed.issubset(have)
            basic['missing_shard_count']=len(needed-have)
        except Exception:basic['index_parse']='HOLD'
    shards=[dir/n for n in files if n.endswith('.safetensors')]
    summaries=[]
    for s in sorted(shards,key=lambda p:p.stat().st_size,reverse=True)[:2]:
        try:summaries.append(safetensors_header(s))
        except Exception:summaries.append(None)
    basic['sample_safetensors_headers']=summaries
    print('NATIVE_V92_MODEL_PROVENANCE='+json.dumps(basic,ensure_ascii=False,sort_keys=True,separators=(',',':'))[:1800])
if 'large_hf' not in tracked:print('NATIVE_V92_MISSING=large_hf')
if 'optimizer_pair' not in tracked:print('NATIVE_V92_MISSING=optimizer_pair')
print('NATIVE_V92_UNSAFE_PICKLE_DESERIALIZATION=false')
print('NATIVE_V92_FULL_WEIGHTS_HASHED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    ssh.REMOTE=REMOTE;ssh.api=settle
    buf=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(buf):ok=ssh.probe()
    except Exception as e:
        v=str(e);print('NOX_V92_HOLD='+v if v.startswith('HOLD_') else 'NATIVE_CONNECTION')
    finally:
        try:
            with contextlib.redirect_stdout(buf):
                if not ssh.cleanup():ok=False
        except Exception:ok=False
    data=buf.getvalue()
    for line in data.splitlines():
        if line.startswith(('NATIVE_V92_','TEMP_SSH_CLEANUP=')) and len(line)<2000:
            print(line)
    passed='NATIVE_V92_MODEL_PROVENANCE=' in data and 'NATIVE_READ_ONLY_COMPLETE=true' in data and ok
    print('NOX_V92_MODEL_PROVENANCE_VERIFIED='+str(bool(passed)).lower())
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
