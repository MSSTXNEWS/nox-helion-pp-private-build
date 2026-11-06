"""NOX LOCAL functional adapters (read-mostly). No model/data changes by default."""
from pathlib import Path
import json, os, re, subprocess, hashlib, sqlite3, time
ROOT=Path(__file__).resolve().parent
LOCAL=Path(os.environ.get('NOX_ROOT',r'C:\NOX_HELION'))
CONFIG=ROOT/'nox_connections.json'

def load_config():
    try: return json.loads(CONFIG.read_text('utf-8'))
    except (OSError,ValueError): return {}

def inside(path,root):
    try: Path(path).resolve().relative_to(Path(root).resolve());return True
    except (ValueError,OSError):return False

def truth_metrics():
    from pc_metrics import read
    try: return read()
    except Exception as e:return {'status':'HOLD','error':str(e),'cpu':None,'ram':None,'gpu':None,'gpu_temperature':None}

def parse_training_line(line):
    # JSONL only: no interpolated or manufactured loss
    try:
        x=json.loads(line)
        if not isinstance(x,dict):return None
        keep={k:x[k] for k in ('loss','train_loss','grad_norm','learning_rate','epoch','global_step','step','num_tokens','train_runtime','train_steps_per_second') if k in x and isinstance(x[k],(int,float))}
        return keep or None
    except (ValueError,TypeError):return None

def training_status():
    c=load_config(); path=c.get('trainer_log'); model=c.get('trainer_source');out={'status':'HOLD','reason':'TRAINER_NOT_CONNECTED','trainable_source':None,'log':None,'checkpoints':[],'can_start':False,'can_resume':False,'can_rollback':False}
    if not isinstance(path,str) or not path or not inside(path,LOCAL):return out
    p=Path(path)
    if not p.is_file():return {**out,'reason':'LOG_NOT_FOUND'}
    try:
        lines=p.read_text('utf-8',errors='replace').splitlines()[-800:]
        records=[x for line in lines if (x:=parse_training_line(line))]
        out.update({'status':'READ_ONLY','reason':'Existing trainer log found; execution adapter not verified','log':{'path':str(p),'last':records[-1] if records else None,'samples':records[-120:]}})
        if isinstance(model,str) and inside(model,LOCAL) and Path(model).exists():out['trainable_source']=model
        cp=c.get('checkpoint_dir')
        if isinstance(cp,str) and inside(cp,LOCAL) and Path(cp).is_dir():
            out['checkpoints']=[{'name':x.name,'size':x.stat().st_size,'updated':int(x.stat().st_mtime)} for x in sorted(Path(cp).glob('*'),key=lambda f:f.stat().st_mtime,reverse=True) if x.is_file()][:30]
    except OSError as e:out['reason']=str(e)
    return out

def s03_status():
    c=load_config(); path=c.get('s03_db')
    if not isinstance(path,str) or not path or not inside(path,LOCAL):return {'status':'HOLD','reason':'Original S03 path not verified'}
    if not Path(path).is_file():return {'status':'HOLD','reason':'Configured S03 path does not exist'}
    try:
        uri=Path(path).resolve().as_uri()+'?mode=ro'
        with sqlite3.connect(uri,uri=True,timeout=2) as db:
            tables=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            return {'status':'READ_ONLY','tables':tables,'reason':'S03 schema compatibility not verified; no writing'}
    except (OSError,sqlite3.Error) as e:return {'status':'HOLD','reason':str(e)}

def push_status():
    c=load_config(); ready=bool(c.get('vapid_private_key') and c.get('vapid_public_key') and c.get('vapid_subject'))
    try: import pywebpush;pkg=True
    except ImportError:pkg=False
    return {'notification_api':True,'service_worker':True,'webpush_server':'READY' if ready and pkg else 'HOLD','reason':None if ready and pkg else 'Need verified VAPID keys, pywebpush and a running event sender (not automatically installed)','browser_close_delivery_verified':False}

def check_services():
    return {'train':training_status(),'s03':s03_status(),'push':push_status(),'timestamp':int(time.time())}