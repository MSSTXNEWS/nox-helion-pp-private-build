#!/usr/bin/env python3
"""Read-only fixed-target OneHost audit. No POST, generation, downloads or source export."""
from __future__ import annotations
import ast
import hashlib
from html.parser import HTMLParser
import http.client
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

SCRIPTS=('scripts/chat_proxy.py','scripts/nox_web29_onehost_18775.py','scripts/nox_v29_chat_bridge.py')
PIDS=(3266857,3367881,3368105)
TUNNEL_FILES=('logs/cloudflared.log','logs/nox-cloudflared.log','logs/web29_tunnel.log',
              'state/tunnel_url.txt','state/public_url.txt')
BLOCKED_HOST='clarity-sit-efficient-has.trycloudflare.com'
TUNNEL=re.compile(r'\b[a-z0-9-]+\.(?:trycloudflare\.com|ngrok-free\.app)\b',re.I)
SENSITIVE=re.compile(r'(?i)(?:\bsk-[a-z0-9_-]{12,}|bearer\s+\S+|(?:password|secret|token|api[_-]?key|cookie|session)[=:])')
MAX_FILE=1024*1024


def read_bytes(path,limit=MAX_FILE):
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size>limit:return None
        with path.open('rb') as file:return file.read(limit+1)
    except OSError:return None


def safe_path(value,root):
    if not isinstance(value,str) or len(value)>512 or '\x00' in value or SENSITIVE.search(value):return None
    candidate=Path(value)
    if not candidate.is_absolute():return None
    try:
        resolved=candidate.resolve()
        if resolved!=root and root not in resolved.parents:return None
        return resolved
    except (OSError,ValueError):return None


def scalar(value,kind='code'):
    if value is None or isinstance(value,(bool,int)):return value
    if isinstance(value,float):return value if value==value and abs(value)<1e20 else None
    if not isinstance(value,str) or len(value)>200 or SENSITIVE.search(value):return None
    pattern=r'[A-Za-z0-9_. /:+-]{1,200}' if kind=='model' else r'[A-Za-z0-9_.:-]{1,100}'
    return value if re.fullmatch(pattern,value) else None


class Assets(HTMLParser):
    def __init__(self):super().__init__();self.refs=[]
    def handle_starttag(self,tag,attrs):
        if tag not in ('script','link','img','audio','video','source'):return
        for key,value in attrs:
            if key not in ('src','href') or not value or len(value)>512:continue
            parsed=urlsplit(value)
            if parsed.hostname==BLOCKED_HOST or parsed.username or parsed.password:continue
            if parsed.scheme in ('data','javascript'):continue
            # Strip queries/fragments; never export inline script/config/session text.
            ref=(parsed.scheme+'://'+parsed.netloc+parsed.path) if parsed.netloc else parsed.path
            if ref and not SENSITIVE.search(ref):self.refs.append(ref)


def html_metadata(raw):
    parser=Assets()
    try:parser.feed(raw.decode('utf-8','replace'))
    except (ValueError,RecursionError):pass
    return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'asset_refs':sorted(set(parser.refs))[:80]}


def source_metadata(path,root):
    raw=read_bytes(path)
    if raw is None:return {'path':str(path),'status':'MISSING_OR_NOT_BOUNDED'},[]
    output={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'source_exported':False}
    try:tree=ast.parse(raw.decode('utf-8'))
    except (SyntaxError,UnicodeDecodeError,RecursionError):return dict(output,ast_status='UNPARSED'),[]
    values={};routes=set();bound=[]
    def evaluate(node):
        if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
        if isinstance(node,ast.Name):return values.get(node.id)
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div):
            left,right=evaluate(node.left),evaluate(node.right)
            if left is not None and right is not None:return str(Path(left)/right)
        if isinstance(node,ast.Call):
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            parts=[evaluate(x) for x in node.args]
            if name in ('Path','str') and len(parts)==1:return parts[0]
            if name=='join' and parts and all(isinstance(x,str) for x in parts):return str(Path(parts[0]).joinpath(*parts[1:]))
        return None
    for node in tree.body:
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            value=evaluate(node.value)
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target,ast.Name) and isinstance(value,str):values[target.id]=value
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            if name in ('get','post','route','mount','add_api_route') and node.args:
                route=evaluate(node.args[0])
                if isinstance(route,str) and re.fullmatch(r'/[A-Za-z0-9_./{}:-]{0,180}',route):routes.add(route)
            if name in ('StaticFiles','SimpleHTTPRequestHandler','send_from_directory'):
                candidates=[evaluate(x.value) for x in node.keywords if x.arg=='directory']
                if name=='send_from_directory' and node.args:candidates.append(evaluate(node.args[0]))
                for value in candidates:
                    resolved=safe_path(value,root)
                    if resolved:bound.append({'path':str(resolved),'evidence':'AST_DIRECTORY_ARGUMENT'})
    for name,value in values.items():
        if re.search(r'(SITE|WEB|ROOT|STATIC|DIRECTORY|HTML)',name,re.I):
            resolved=safe_path(value,root)
            if resolved:bound.append({'path':str(resolved),'evidence':'AST_PATH_CONSTANT','symbol':name[:80]})
    # Constant candidates are labelled as candidates, never claimed actual routing.
    output.update(ast_status='PARSED',routes=sorted(routes),directory_bindings=bound[:20])
    return output,bound[:20]


def loopback_get(port,path,connection_factory=None):
    if (port,path) not in ((18775,'/api/nox/status'),(18775,'/nox-web-v29/pc/resonance.html'),(8098,'/health'),(8098,'/slots')):
        return {'status':'TARGET_NOT_ALLOWED'},None
    conn=(connection_factory or http.client.HTTPConnection)('127.0.0.1',port,timeout=1.5)
    try:
        conn.request('GET',path,headers={'Accept':'application/json,text/html','Accept-Encoding':'identity','Connection':'close'})
        response=conn.getresponse();raw=response.read(262145)
        meta={'http_status':response.status,'port':port,'path':path,'redirect_followed':False}
        if len(raw)>262144:return dict(meta,body_status='SIZE_LIMIT'),None
        if response.status!=200:return meta,None
        return meta,raw
    except (OSError,http.client.HTTPException):return {'port':port,'path':path,'status':'READ_UNAVAILABLE'},None
    finally:conn.close()


def filter_json(raw,kind):
    try:value=json.loads(raw)
    except (ValueError,UnicodeDecodeError,RecursionError):return {'parse_status':'INVALID_OR_NON_JSON'}
    if kind=='slots':
        if not isinstance(value,list):return {'parse_status':'UNEXPECTED_SCHEMA'}
        keys=('id','id_task','state','is_processing','n_ctx','n_past','n_predict','n_decoded')
        return {'slots':[{k:scalar(v) for k,v in item.items() if k in keys and scalar(v) is not None} for item in value[:8] if isinstance(item,dict)],'prompt_fields_exported':False}
    if not isinstance(value,dict):return {'parse_status':'UNEXPECTED_SCHEMA'}
    keys=('status','backend','primary_model','native_p02_bound','native_cognitive_memory_bound','native_dialogs_ready','chat_active','mode')
    output={k:scalar(v,'model' if k=='primary_model' else 'code') for k,v in value.items() if k in keys and scalar(v,'model' if k=='primary_model' else 'code') is not None}
    model=value.get('model')
    if isinstance(model,str):output['model']=scalar(model,'model')
    elif isinstance(model,dict):output['model']={k:scalar(model[k],'model') for k in ('name','id','model') if k in model and scalar(model[k],'model') is not None}
    return output


def owner_state(root):
    out={}
    for name in ('CHAT_ACTIVE','MODE','IDLE_MINUTES','TRAIN_PAUSE','KNOWLEDGE_PAUSE','LAST_OWNER_CHAT'):
        raw=read_bytes(root/'state/priority'/name,512)
        if raw is None:continue
        text=raw.decode('ascii','ignore').strip()
        if name=='LAST_OWNER_CHAT':
            if re.fullmatch(r'[0-9.TZ:+ -]{1,50}',text):out[name]=text
        elif scalar(text) is not None:out[name]=scalar(text)
    raw=read_bytes(root/'state/priority/status.json',32768)
    if raw:
        try:data=json.loads(raw)
        except (ValueError,UnicodeDecodeError):data={}
        allowed=('mode','chat_active','idle_minutes','active_request_count','training_paused','knowledge_paused')
        if isinstance(data,dict):out['status']={k:scalar(v) for k,v in data.items() if k in allowed and scalar(v) is not None}
    out['train_pause_request_flag_exists']=(root/'state/TRAIN_PAUSE_REQUEST.flag').is_file()
    return out


def cgroup_snapshot(proc_root,cgroup_root):
    raw=read_bytes(proc_root/'self/cgroup',4096);out={'status':'UNRESOLVED'}
    if not raw:return out
    rows=raw.decode('utf-8','replace').splitlines()
    path=next((x.split(':',2)[2] for x in rows if x.startswith('0::')),None)
    if path is None:return out
    candidate=(cgroup_root/path.lstrip('/')).resolve()
    if candidate!=cgroup_root and cgroup_root not in candidate.parents:return out
    if not (candidate/'memory.stat').is_file():return out
    out={'status':'READ','cgroup_path_sha256':hashlib.sha256(path.encode()).hexdigest()}
    for name in ('memory.current','memory.max','memory.high'):
        value=read_bytes(candidate/name,256)
        if value:
            value=value.decode().strip()
            if value=='max' or value.isdigit():out[name]=value
    stat=read_bytes(candidate/'memory.stat',16384)
    if stat:
        allowed={'anon','file','shmem','file_mapped','file_dirty','file_writeback','inactive_file','active_file','slab','sock','pagetables','kernel'}
        out['memory.stat']={k:int(v) for row in stat.decode().splitlines() if len((pair:=row.split()))==2 for k,v in [pair] if k in allowed and v.isdigit()}
    pressure=read_bytes(candidate/'memory.pressure',2048)
    if pressure:
        out['memory.pressure']={}
        for row in pressure.decode().splitlines():
            parts=row.split()
            if parts and parts[0] in ('some','full'):
                out['memory.pressure'][parts[0]]={k:float(v) for item in parts[1:] if '=' in item for k,v in [item.split('=',1)] if k in ('avg10','avg60','avg300','total') and re.fullmatch(r'[0-9.]+',v)}
    out['cache_reclaimability']='NOT_ASSUMED'
    return out


def run_probe(root=Path('/root/nox'),proc_root=Path('/proc'),cgroup_root=Path('/sys/fs/cgroup'),fetch=loopback_get):
    started=time.monotonic();root=root.resolve();cgroup_root=cgroup_root.resolve()
    audit={'schema':'NOX_CHAT_LAUNCH_READONLY_AUDIT_V1','observed_at_epoch':time.time(),'native_mutations':False,'generation_calls':0,'source_exported':False}
    scripts=[];dirs=[]
    for rel in SCRIPTS:
        info,bindings=source_metadata(root/rel,root);scripts.append(info);dirs.extend(bindings)
    audit['scripts']=scripts
    html=[];seen=set()
    for binding in dirs:
        for relative in ('pc/resonance.html','resonance.html','index.html'):
            path=Path(binding['path'])/relative
            if str(path) in seen or safe_path(str(path),root) is None:continue
            seen.add(str(path));raw=read_bytes(path,262144)
            if raw is not None:html.append({'directory':binding['path'],'relative_path':relative,'binding_evidence':binding['evidence'],**html_metadata(raw)})
    audit['html_candidates']=html[:20]
    network=[]
    for port,path,kind in ((18775,'/api/nox/status','status'),(8098,'/health','health'),(8098,'/slots','slots'),(18775,'/nox-web-v29/pc/resonance.html','html')):
        meta,raw=fetch(port,path)
        if raw is not None:meta['selected_metadata']=html_metadata(raw) if kind=='html' else filter_json(raw,kind)
        network.append(meta)
    audit['loopback_reads']=network
    audit['owner_state']=owner_state(root);audit['cgroup']=cgroup_snapshot(proc_root,cgroup_root)
    processes=[];tunnels=[]
    for pid in PIDS:
        raw=read_bytes(proc_root/str(pid)/'cmdline',65536)
        if raw:
            argv=[x.decode('utf-8','replace') for x in raw.split(b'\0') if x]
            names=[str(p) for item in argv if (p:=safe_path(item,root)) is not None]
            flags={}
            for i,item in enumerate(argv[:-1]):
                if item in ('--port','-c','--ctx-size','-np','--parallel','--n-cpu-moe','--moe-cache-mib','-ctk','-ctv') and scalar(argv[i+1]) is not None:flags[item]=scalar(argv[i+1])
            processes.append({'pid':pid,'script_or_model_paths':names[:12],'selected_flags':flags})
            tunnels.extend({'host':h.lower(),'source':'fixed_pid_argv','pid':pid} for h in TUNNEL.findall('\n'.join(argv)) if h.lower()!=BLOCKED_HOST)
    for relative in TUNNEL_FILES:
        path=root/relative
        try:
            if not path.is_file() or path.is_symlink():continue
            with path.open('rb') as file:
                file.seek(max(0,path.stat().st_size-65536));text=file.read(65536).decode('utf-8','replace')
        except OSError:continue
        tunnels.extend({'host':h.lower(),'source':relative} for h in sorted(set(TUNNEL.findall(text))) if h.lower()!=BLOCKED_HOST)
    audit['processes']=processes;audit['public_tunnel_candidates']=tunnels[:20]
    audit['external_http_calls']=0;audit['elapsed_seconds']=round(time.monotonic()-started,3)
    return audit


def main():
    try:
        audit=run_probe();complete=True
    except Exception:
        # No raw exception/source/config/private response may escape to job logs.
        audit={'schema':'NOX_CHAT_LAUNCH_READONLY_AUDIT_V1','status':'BOUNDED_AUDIT_ERROR','native_mutations':False};complete=False
    print('NOX_MAINT_AUDIT='+json.dumps(audit,ensure_ascii=False,separators=(',',':')))
    print('NOX_MAINT_AUDIT_COMPLETE='+str(complete).lower())

if __name__=='__main__':main()
