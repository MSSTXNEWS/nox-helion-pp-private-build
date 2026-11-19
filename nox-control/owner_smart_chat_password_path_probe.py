#!/usr/bin/env python3
"""Read-only AST shape probe for the owner password path; no secret values exported."""
from __future__ import annotations
import ast, hashlib, json, os, re, stat
from pathlib import Path
P=Path('/root/nox/scripts/chat_proxy.py')
EXPECTED='cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb'
def shape(n,depth=0):
    if depth>8:return {'node':'TRUNCATED'}
    if isinstance(n,ast.Name):return {'node':'Name','id':n.id[:80]}
    if isinstance(n,ast.Attribute):return {'node':'Attribute','attr':n.attr[:80],'on':shape(n.value,depth+1)}
    if isinstance(n,ast.Constant):return {'node':'Constant','type':type(n.value).__name__,'length':len(n.value) if isinstance(n.value,str) else 0}
    if isinstance(n,ast.Call):return {'node':'Call','func':shape(n.func,depth+1),'args':[shape(x,depth+1) for x in n.args[:5]],'keywords':[(x.arg or '')[:80] for x in n.keywords[:5]]}
    if isinstance(n,ast.BinOp):return {'node':'BinOp','op':type(n.op).__name__,'left':shape(n.left,depth+1),'right':shape(n.right,depth+1)}
    if isinstance(n,ast.Subscript):return {'node':'Subscript','value':shape(n.value,depth+1),'slice':shape(n.slice,depth+1)}
    if isinstance(n,ast.IfExp):return {'node':'IfExp','body':shape(n.body,depth+1),'orelse':shape(n.orelse,depth+1)}
    return {'node':type(n).__name__}
def main():
    req=os.getenv('NOX_OWNER_REQUEST_ID','');sha=os.getenv('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch(r'[0-9]{1,24}',req) or not re.fullmatch(r'[a-f0-9]{40}',sha):raise ValueError('OWNER_CONTEXT')
    meta=P.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_size>1048576 or meta.st_nlink!=1:raise ValueError('SOURCE_SCOPE')
    raw=P.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('SOURCE_SHA')
    tree=ast.parse(raw);found=[]
    for n in tree.body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
            name=n.targets[0].id
            if name=='CHAT_PASSWORD_PATH':found.append({'name':name,'shape':shape(n.value)})
            elif name in ('ROOT','STATE','BASE_DIR','NOX_ROOT','ROOT_DIR','CONFIG_DIR','PASSWORD_DIR','NOX_STATE','SECRETS','BASE','NOX_HOME'):
                found.append({'name':name,'shape':shape(n.value)})
        if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='CHAT_PASSWORD_PATH':
            found.append({'name':'CHAT_PASSWORD_PATH','shape':shape(n.value)})
    bindings=[]
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'SECRETS' for t in n.targets):
            bindings.append({'binding':'Assign','line':n.lineno,'shape':shape(n.value)})
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id=='SECRETS':
            bindings.append({'binding':'AnnAssign','line':n.lineno,'shape':shape(n.value)})
        elif isinstance(n, ast.ImportFrom) and any(a.name=='SECRETS' or a.asname=='SECRETS' for a in n.names):
            bindings.append({'binding':'ImportFrom','module':(n.module or '')[:100]})
        elif isinstance(n, ast.Import) and any(a.asname=='SECRETS' for a in n.names):
            bindings.append({'binding':'Import'})
    found.append({'name':'SECRETS_BINDINGS','shapes':bindings[:12]})
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'owner_password_path_ast','data':{'request':req,'source_sha':sha,
       'no_password_read':True,'no_secrets_exported':True,'assignments':found[:16]}},separators=(',',':')),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
if __name__=='__main__':main()
