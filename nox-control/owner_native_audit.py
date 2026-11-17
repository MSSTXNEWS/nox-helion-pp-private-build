#!/usr/bin/env python3
"""Read only: identify existing owner credential reader and native bridge pins."""
import ast, hashlib, json, re, time
from pathlib import Path

ROOT=Path('/root/nox')
SAFE_PATH=re.compile(r'^/root/nox/[A-Za-z0-9_./-]{1,220}$')
SAFE_NAME=re.compile(r'^[A-Z_][A-Z0-9_]{1,95}$')
TARGETS={'_read_chat_password','_session_ok','_unauthorized','chat_login','login'}

def read(path,limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:return None
    with path.open('rb') as f:return f.read(limit+1)

def redact_tree(node):
    keep=set()
    for item in ast.walk(node):
        if isinstance(item,ast.Call) and isinstance(item.func,ast.Attribute) and item.func.attr in ('get','getenv') and item.args:
            key=item.args[0]
            owner=item.func.value
            name=owner.attr if isinstance(owner,ast.Attribute) else owner.id if isinstance(owner,ast.Name) else ''
            if name in ('os','environ') and isinstance(key,ast.Constant) and isinstance(key.value,str) and SAFE_NAME.fullmatch(key.value):keep.add(id(key))
    class Redact(ast.NodeTransformer):
        def visit_Constant(self,n):
            if id(n) in keep or n.value is None or isinstance(n.value,bool):return n
            if isinstance(n.value,str) and SAFE_PATH.fullmatch(n.value) and '..' not in Path(n.value).parts:return n
            return ast.copy_location(ast.Constant(value='<REDACTED_VALUE>'),n)
    return ast.unparse(ast.fix_missing_locations(Redact().visit(node)))

def pin(path):
    raw=read(path,150000)
    return {'path':str(path),'exists':raw is not None,**({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} if raw is not None else {})}

def run():
    p=ROOT/'scripts/chat_proxy.py';raw=read(p,150000)
    out={'schema':'NOX_OWNER_AUTH_READER_PROBE_V1','observed_at_epoch':time.time(),'http_requests':0,'native_mutations':False,'credential_values_exported':False,'proxy':pin(p)}
    if raw is not None:
        tree=ast.parse(raw.decode());functions=[];assignments=[];names=[]
        for n in tree.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                if re.search('auth|session|password|login',n.name,re.I):names.append(n.name)
                if n.name in TARGETS or re.search('(?:read|load).*password|password.*(?:read|load)',n.name,re.I):functions.append(redact_tree(n))
            elif isinstance(n,(ast.Assign,ast.AnnAssign)):
                targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                identifiers=[x.id for t in targets for x in ast.walk(t) if isinstance(x,ast.Name)]
                if any(re.search('AUTH|PASS|SESSION|COOKIE|CONFIG|ROOT',x) for x in identifiers):assignments.append(redact_tree(n))
        out['auth_function_names']=names;out['auth_readers']=functions;out['auth_config_assignments']=assignments
    web=read(ROOT/'scripts/nox_web29_onehost_18775.py',16384)
    if web:
        for n in ast.parse(web).body:
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='UPSTREAM' for t in n.targets) and isinstance(n.value,ast.Constant):
                value=n.value.value
                if isinstance(value,str) and re.fullmatch(r'http://127\.0\.0\.1:[0-9]{2,5}/?',value):out['web_loopback_upstream']=value
    out['existing_helpers']=[pin(ROOT/'scripts'/name) for name in ('owner_drive_ram_bridge.py','owner_drive_ram_prepare.py','owner_drive_storage_bridge.py','owner_hermes_hydrate.py','owner_subagent_dispatcher_fresh.py')]
    out['tunnels']=[]
    for p in list(Path('/proc').glob('[0-9]*/cmdline'))[:2048]:
        try:
            raw=p.read_bytes()[:8192]
            if b'cloudflared' not in raw:continue
            args=raw.decode(errors='replace').split('\0')
            local=[a for a in args if re.fullmatch(r'http://(?:127\.0\.0\.1|localhost):[0-9]{2,5}',a)]
            out['tunnels'].append({'pid':int(p.parent.name),'local_targets':local,'token_values_exported':False})
        except OSError:pass
    out['tunnel_hostnames_from_native_logs']=[]
    logs=[]
    for pat in ('*cloudflar*.log','*tunnel*.log'):
        logs.extend(list((ROOT/'logs').glob(pat))[:12])
    for p in list(dict.fromkeys(logs))[:20]:
        try:
            if p.is_symlink() or not p.is_file():continue
            with p.open('rb') as f:
                f.seek(max(0,p.stat().st_size-65536));txt=f.read(65536).decode(errors='replace')
            hosts=sorted(set(re.findall(r'https://([a-z0-9-]{4,100}\.trycloudflare\.com)',txt)))
            if hosts:out['tunnel_hostnames_from_native_logs'].append({'log_path':str(p),'hostnames':hosts[-4:],'mtime_epoch':p.stat().st_mtime})
        except OSError:pass
    return out

if __name__=='__main__':
    try:result=run();good=True
    except Exception as exc:result={'status':'HOLD','error_type':type(exc).__name__};good=False
    print('NOX_MAINT_AUDIT='+json.dumps(result,ensure_ascii=False,separators=(',',':')))
    print('NOX_MAINT_AUDIT_COMPLETE='+str(good).lower())
