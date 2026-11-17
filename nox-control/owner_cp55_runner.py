"""Existing owner issue-comment authorization and SSH, binary ciphertext only."""
import base64, hashlib, json, os, re, selectors, subprocess, sys, time
from pathlib import Path
import owner_cp55_cipher as core
import auth_prefix_reuse as auth

PACKAGE=Path(__file__).resolve().parent
def package_script(public,source,request):
    pins=json.loads((PACKAGE/'CP55_SOURCE_PINS.json').read_bytes())
    modules={}
    for name in ('owner_cp55_scope','owner_cp55_cipher','owner_cp55_native'):
        raw=(PACKAGE/(name+'.py')).read_bytes();core.require(core.sha(raw)==pins[name+'.py'],'SOURCE_PIN')
        modules[name]=base64.b64encode(raw).decode()
    raw_public=(PACKAGE/'owner_cp55_public.json').read_bytes()
    core.require(core.sha(raw_public)==pins['owner_cp55_public.json'],'PUBLIC_PIN')
    core.public_key(public,pins['owner_cp55_scope.py'])
    script=('import sys,base64,types,json,re\nsys.dont_write_bytecode=True\n'
            'modules='+repr(modules)+'\n'
            'for name,value in modules.items():\n m=types.ModuleType(name);sys.modules[name]=m;exec(compile(base64.b64decode(value),"<reviewed-cp55-backup>","exec"),m.__dict__)\n'
            'try:\n r=sys.modules["owner_cp55_native"].export('+repr(public)+','+repr(pins['owner_cp55_scope.py'])+','+repr(source)+','+repr(str(request))+',sys.stdout.buffer)\n'
            ' print("NOX_CP55_NATIVE="+json.dumps(r,separators=(",",":")),file=sys.stderr,flush=True)\n'
            'except Exception as e:\n s=str(e);s=s if re.fullmatch("HOLD_[A-Z0-9_]+",s) else "HOLD_CP55_NATIVE_"+type(e).__name__.upper()\n print(s,file=sys.stderr,flush=True);raise SystemExit(2)\n')
    core.require(len(script.encode())<160000,'SCRIPT_BOUND');return script.encode()

def receive(common,host,script,parts):
    command=common+['-o','ControlMaster=no','-o','ProxyCommand=false',host,'env','PYTHONNOUSERSITE=1','/usr/bin/python3','-I','-B','-']
    child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    diagnostics=bytearray();deadline=time.monotonic()+930
    try:
        child.stdin.write(script);child.stdin.close()
        with selectors.DefaultSelector() as select:
            select.register(child.stdout,selectors.EVENT_READ,'out');select.register(child.stderr,selectors.EVENT_READ,'err')
            while select.get_map():
                core.require(time.monotonic()<deadline,'DEADLINE')
                for key,_ in select.select(1):
                    block=os.read(key.fd,core.BLOCK)
                    if not block:select.unregister(key.fileobj);continue
                    if key.data=='out':parts.write(block)
                    else:diagnostics.extend(block);core.require(len(diagnostics)<32768,'DIAGNOSTIC_BOUND')
        code=child.wait(timeout=5)
        rows=[];reason='HOLD_CP55_NATIVE_EXPORT'
        for line in bytes(diagnostics).splitlines():
            if line.startswith(b'NOX_CP55_NATIVE='):rows.append(json.loads(line.split(b'=',1)[1]))
            elif re.fullmatch(rb'HOLD_[A-Z0-9_]+',line):reason=line.decode()
        if code or len(rows)!=1:raise RuntimeError(reason)
        row=rows[0];core.require(row.get('stop_flags_unchanged') is True and row.get('temporary_ram_snapshot_removed') is True and row.get('source_deleted') is False,'NATIVE_RECEIPT')
        return row
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=5)
        parts.close_part()

def main():
    # Same exact OWNER/issue256/comment/source checks as existing maintenance.
    import owner_native_operator as operator
    core.require(os.environ.get('GITHUB_RUN_ATTEMPT')=='1','NO_REPLAY_ATTEMPT')
    request=operator.authorize_event('backup');source=os.environ['NOX_PINNED_SOURCE_SHA']
    print('NOX_MAINT_AUTHORIZED_COMMENT_ID='+str(request),flush=True)
    public=json.loads((PACKAGE/'owner_cp55_public.json').read_bytes());script=package_script(public,source,request)
    ns=None;result=None;good=False
    try:
        ns=auth.authentication_namespace();common,host,_=ns['run_native']('backup',request)
        output=auth.REPOSITORY/'artifacts/cp55-s03-cipher';output.parent.mkdir(mode=0o700,exist_ok=True)
        parts=core.Parts(output);native=receive(common,host,script,parts)
        # Complete source receipt exists only after native success + full part readback.
        result=parts.finish();reader=core.PartReader(output,result)
        while reader.read(core.BLOCK):pass
        good=True
    finally:
        if ns is not None and not auth.cleanup(ns):good=False
    core.require(good,'TEMPORARY_SSH_KEY_CLEANUP')
    result.update(source=source,request=str(request),native=native,local_restore_verified=False,drive_copy_verified=False)
    core.private_write(output/'EXPORT_VERIFIED.json',core.canonical(result)+b'\n')
    print(json.dumps({'state':'CIPHERTEXT_READY_LOCAL_RESTORE_REQUIRED','parts':len(result['parts']),
        'ciphertext_bytes':result['bytes'],'ciphertext_sha256':result['sha256'],'temporary_ssh_key_removed':True,
        'source_deleted':False,'local_restore_verified':False,'drive_copy_verified':False}),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:
        reason=str(e);reason=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else 'HOLD_CP55_RUNNER_'+type(e).__name__.upper()
        print(reason,flush=True);raise SystemExit(2)
