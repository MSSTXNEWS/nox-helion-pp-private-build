"""E2 V83: one native read-only diagnosis of actual Forge failure and web stream.

Only existing V51 NOX2/Vast SSH access. No GPU training, model downloads,
service restarts, new servers or raw chat/medical/secret data exported.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn

_original=conn.api
def settle(method,path,key,data=None):
    result=_original(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(13)
    return result

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,html.parser,json,os,re,sqlite3,subprocess,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V83_SCHEMA=NOX_E2_FORGE_AND_STREAM_FAULT_ISOLATION_V1')

def emit(label,data):
    print(label+'='+json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'))[:650])

def safe_supervisor(name):
    try:
        p=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=8)
        words=p.stdout.strip().split()
        return words[1] if p.returncode==0 and len(words)>1 else 'UNKNOWN'
    except (OSError,subprocess.TimeoutExpired):
        return 'UNKNOWN'
names=('nox-proxy','nox-chat-8081','nox-train-volta-t866u',
    'nox-train-worm-t811u','nox-distill-worm-t811u','nox-cores',
    'nox-embed','nox-priority-scheduler','nox-teacher-serve-t811u')
emit('NATIVE_V83_SERVICES',{name:safe_supervisor(name) for name in names})

# Extract only classification bits, never full stack traces/private user data.
signals={
 'TRAIN_ERROR_STEP0':r'train_error.{0,20}step.{0,3}0\b',
 'MISSING_TRAINABLE_MODEL':r'GGUF.{0,30}(?:train|error|unsupported)|safetensors.{0,24}(?:missing|not found)',
 'CUDA_OUT_OF_MEMORY':r'(?:CUDA|GPU).{0,10}(?:out of memory|OOM)',
 'TORCH_KERNEL_VOLTA':r'(?:bf16|flash.attn|sm70|compute capability|kernel image)',
 'PERMISSION':r'PermissionError|permission denied',
 'DATA_MISSING':r'(?:dataset|training data|jsonl).{0,30}(?:not found|empty|missing|invalid)',
 'OPTIMIZER_MISSING':r'(?:optimizer|checkpoint).{0,35}(?:not found|missing|incompatible)',
 'MODEL_IMPORT':r'ModuleNotFoundError|ImportError',
 'STEP_OR_EPOCH':r'(?:global_step|optimizer.step|step=|step\s+\d+)',
 'TRACEBACK':r'Traceback \(most recent call last\)',
 'KILLED':r'Killed|exit status -9|exit status 137',
}
for service in ('nox-train-volta-t866u','nox-train-worm-t811u','nox-distill-worm-t811u'):
    try:
        p=subprocess.run(['supervisorctl','tail','-200',service,'stderr'],
           capture_output=True,text=True,timeout=9)
        text=(p.stdout if p.returncode==0 else '')[-25000:]
        found=[key for key,pat in signals.items() if re.search(pat,text,re.I|re.S)]
        nums=[int(m.group(1)) for m in re.finditer(r'\b(?:global_step|step)[=: ]{1,3}([0-9]{1,7})\b',text,re.I)]
        emit('NATIVE_V83_TRAIN_ERROR_CLASS',{'service':service,
             'log_available':bool(text),'signals':found,
             'maximum_step_in_recent_log':max(nums) if nums else None,
             'source_text_exported':False})
    except (OSError,subprocess.TimeoutExpired):
        emit('NATIVE_V83_TRAIN_ERROR_CLASS',{'service':service,'state':'HOLD_LOG_UNAVAILABLE'})

def scan(root,depth_limit=4,cap=250):
    p=Path(root);dirs=0;models=0;weights=0;optimizers=0;checkpoints=0;configs=0
    total_weight_bytes=0
    if not p.is_dir():
        return {'present':False}
    for parent,dnames,fnames in os.walk(p,followlinks=False):
        level=len(Path(parent).relative_to(p).parts)
        dnames[:]=[x for x in dnames if level<depth_limit and not
             (Path(parent)/x).is_symlink()][:70]
        dirs+=1
        if 'config.json' in fnames:configs+=1
        for name in fnames:
            try:
                f=Path(parent)/name
                if not f.is_file() or f.is_symlink():continue
                size=f.stat().st_size
                if name.endswith(('.safetensors','.bin')) and size>10_000_000:
                    weights+=1;total_weight_bytes+=size
                if name.endswith('.gguf') and size>100_000_000:models+=1
                if 'optimizer' in name.lower(): optimizers+=1
                if 'checkpoint' in name.lower(): checkpoints+=1
            except OSError:pass
        if dirs>=cap:break
    return {'present':True,'dirs_scanned':dirs,'model_gguf_files':models,
        'hf_config_files':configs,'weight_shards':weights,
        'weight_shards_total_bytes':total_weight_bytes,
        'optimizer_name_files':optimizers,'checkpoint_name_files':checkpoints}
for root,label in (('/root/nox/models','MODELS'),('/root/nox/training','TRAINING'),
                   ('/root/nox/forge','FORGE'),('/root/nox/checkpoints','CHECKPOINTS')):
    emit('NATIVE_V83_VAULT',{'type':label,**scan(root)})

# Exact existing worker source hashes, function names only.
for f in ('/root/nox/scripts/train_volta_t866u.py',
          '/root/nox/scripts/train_worm_t811u.py',
          '/root/nox/scripts/chat_proxy.py'):
    p=Path(f)
    if not p.is_file() or p.stat().st_size>160000:continue
    data=p.read_bytes()
    try:
        t=ast.parse(data)
        funcs=[n.name for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    except SyntaxError:funcs=[]
    selected=[n for n in funcs if any(k in n for k in
                    ('train','step','load','loop','stream','s03','owner','proxy','restore'))]
    emit('NATIVE_V83_LIVE_SOURCE',{'basename':p.name,'sha256':hashlib.sha256(data).hexdigest(),
        'functions':selected[:22],'source_exported':False})

# Current actual inline chat JS behavior, without showing raw JS.
class HTML(html.parser.HTMLParser):
    def __init__(self):super().__init__();self.active=False;self.scripts=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='script':self.active=True
    def handle_endtag(self,tag):
        if tag.lower()=='script':self.active=False
    def handle_data(self,data):
        if self.active and len(data)<150000:self.scripts.append(data)
try:
    with urllib.request.urlopen('http://127.0.0.1:8080/chat',timeout=4) as r:
        markup=r.read(120000).decode('utf-8','replace')
    parser=HTML();parser.feed(markup)
    js='\n'.join(parser.scripts)
    emit('NATIVE_V83_STREAM_CLIENT',{'inline_js_bytes':len(js),
      'uses_stream':"stream: true" in js or "stream:true" in js,
      'reader':js.count('getReader('),
      'read_loop':js.count('.read()'),
      'raf':js.count('requestAnimationFrame'),
      'sse_parser':js.count('data:'),
      'done_marker':js.count('[DONE]'),
      'proxy_route':js.count('/chat/api'),
      'auth_cookie_required':True,
      'inline_js_sha256':hashlib.sha256(js.encode()).hexdigest(),
      'raw_code_exported':False})
except Exception:
    emit('NATIVE_V83_STREAM_CLIENT',{'state':'HOLD_NO_AUTHORIZED_UI_SOURCE'})

print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    conn.REMOTE=REMOTE
    conn.api=settle
    output=io.StringIO()
    ok=False
    try:
        with contextlib.redirect_stdout(output):
            ok=conn.probe()
    except Exception as ex:
        msg=str(ex)
        print('NOX_V83_STATE='+msg if msg.startswith('HOLD_') and len(msg)<90 else 'NOX_V83_STATE=HOLD_NATIVE_CONNECTION')
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if not conn.cleanup():ok=False
        except Exception:ok=False
    for line in output.getvalue().splitlines():
        if line.startswith(('NATIVE_V83_','TEMP_SSH_CLEANUP=')) and len(line)<800:
            print(line)
    print('NOX_V83_NATIVE_READONLY_PASS='+str(ok).lower())
    return 0 if ok else 2

if __name__=='__main__':
    raise SystemExit(main())
