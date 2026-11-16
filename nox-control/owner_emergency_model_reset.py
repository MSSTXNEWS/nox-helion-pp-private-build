#!/usr/bin/env python3
"""Owner-approved MODEL_UPDATE: stop old NOX services and remove exact old GGUF.
No deletion of memory, checkpoints, optimizer, original code or secret stores.
Runs ONLY through pinned owner SSH issue #256 / existing OneHost #60509551.
"""
import fcntl,hashlib,json,os,re,signal,sqlite3,stat,subprocess,tempfile,time
from pathlib import Path
ROOT=Path('/root/nox'); STATE=ROOT/'state'
SOURCE=os.environ.get('NOX_OWNER_SOURCE_SHA',''); REQUEST=os.environ.get('NOX_OWNER_REQUEST_ID','')
PREFIX='NOX_MAINT_REPAIR='
# Native 2026-11-16 read-only inventory, exact old file path AND byte count.
OLD={
'/root/nox/progress_pull_t784u/gguf/nox36-mix_final_pref-Q4_K_M.gguf':21836629568,
'/root/nox/models/nox-s1-l05-Q4_K_M.gguf':5629108832,
'/root/nox/models/bge-m3-Q4_K_M.gguf':437778496,
'/root/nox/models/teachers/Dolphin3.0-Llama3.1-8B-Q4_K_M.gguf':4920745856,
'/root/nox/models/teachers/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf':4920733824,
'/root/nox/models/teachers/NousResearch_DeepHermes-3-Llama-3-8B-Preview-Q4_K_M.gguf':4920740800,
'/root/nox/models/teachers/saiga_nemo_12b.Q4_K_M.gguf':7477204832,
'/root/nox/models/teachers/vikhr-nemo-12b-instruct-r-21-09-24-q4_k_m.gguf':7477218656,
}
ALIASES=(
'/root/nox/models/current.gguf',
'/root/nox/models/current.gguf.bak_t856u',
'/root/nox/models/teachers/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf',
'/root/nox/models/judge/Qwen3Guard-Gen-4B.Q4_K_M.gguf',
)
FIRST=('nox-lifeline-guard','nox-selfheal','nox-priority-scheduler','nox-dispatcher-t855u','nox-proxy')
def checked(v,why):
    if not v:raise RuntimeError('HOLD_RESET_'+why)
def invoke(args,timeout=30):
    p=subprocess.run(args,capture_output=True,text=True,shell=False,timeout=timeout)
    return p.returncode,p.stdout
def supervisor():
    rc,out=invoke(['supervisorctl','status'],20)
    checked(rc in (0,3),'SUPERVISOR')
    rows={}
    for line in out.splitlines():
        v=line.split()
        if len(v)>=2 and re.fullmatch(r'[A-Za-z0-9_.:-]+',v[0]) and re.fullmatch('[A-Z]+',v[1]):
            rows[v[0]]=v[1]
    checked('nox-dispatcher-t855u' in rows,'ORIGINAL_ONEHOST')
    return rows
def identity(pid):
    try:
        p=Path('/proc')/str(pid)
        fields=(p/'stat').read_text().split(') ',1)[1].split()
        args=[x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(b'\0') if x]
        return int(fields[19]),args
    except (FileNotFoundError,OSError,ValueError,IndexError):return None
def oldchat():
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        v=identity(p.name)
        if v is None:continue
        start,args=v
        if not args or Path(args[0]).name!='llama-server':continue
        if '-m' not in args or '--port' not in args:continue
        if args.index('-m')+1>=len(args) or args.index('--port')+1>=len(args):continue
        if args[args.index('-m')+1]=='/root/nox/models/current.gguf' and args[args.index('--port')+1]=='8081':
            found.append((int(p.name),start))
    return found
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def save(path,obj):
    raw=(json.dumps(obj,ensure_ascii=False,sort_keys=True)+'\n').encode()
    fd,p=tempfile.mkstemp(prefix='.reset-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(p,path)
    finally:
        if os.path.exists(p):os.unlink(p)
def no_open():
    """Targeted in-use check after all native NOX services and detached chat stop.

    The previous all-proc/maps scanner was excessively broad and blocked on
    unrelated inaccessible platform processes. fuser checks precisely each
    old weight file, including mappings held by other visible PIDs. No wildcard.
    """
    import shutil
    tool=shutil.which('fuser')
    if tool is None:return None
    used=set()
    for name,size in OLD.items():
        p=Path(name)
        if not p.is_file() or p.is_symlink():continue
        try:
            result=subprocess.run([tool,'-s','--',str(p)],
                                  capture_output=True,timeout=15,shell=False)
        except (OSError,subprocess.TimeoutExpired):return None
        if result.returncode==0:
            st=p.stat(follow_symlinks=False)
            used.add((st.st_dev,st.st_ino))
        elif result.returncode!=1:return None
    return used

def main():
    checked(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',SOURCE or '') and REQUEST.isdigit(),'OWNER_CONTEXT')
    checked(ROOT.is_dir() and STATE.is_dir() and not STATE.is_symlink(),'EXACT_HOST')
    fd=os.open(STATE/'owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=STATE/('owner_emergency_reset_'+REQUEST+'.json')
        checked(not path.exists(),'REQUEST_REPEAT')
        result={'schema':'NOX_OWNER_EMERGENCY_RESET_V1','source_sha':SOURCE,'request':REQUEST,
                'mode':'MODEL_UPDATE','stopped':[],'stop_failed':[],'deleted':[],'deletion_holds':[],'aliases_removed':[]}
        save(path,result)
        before=supervisor(); chats=oldchat()
        result['original_services']={k:v for k,v in before.items() if k.startswith('nox-')}
        result['old_chat_pids']=[p for p,_ in chats]
        # Owner STOP and maintenance fence remain after this action to inhibit restarts.
        for f in (ROOT/'STOP',STATE/'OWNER_MAINTENANCE.flag'):
            checked(not f.is_symlink(),'FLAG_SYMLINK')
            if not f.exists():
                x=os.open(f,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
                with os.fdopen(x,'w') as t:t.write('OWNER_MODEL_UPDATE '+REQUEST+'\n');t.flush();os.fsync(t.fileno())
        result['maintenance_flags_active']=True
        # A database backup is required BEFORE stopping/deleting. Protect all other S03/source/history.
        db=ROOT/'kb/knowledge.sqlite'
        checked(db.is_file() and not db.is_symlink(),'S03_MISSING')
        directory=ROOT/'backup/owner_emergency'/REQUEST
        checked(not directory.exists() and not directory.is_symlink(),'BACKUP_COLLISION')
        directory.mkdir(parents=True,mode=0o700)
        dest=directory/'knowledge.sqlite'
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=8) as src:
            with sqlite3.connect(str(dest),timeout=8) as dst:src.backup(dst,pages=256,sleep=.04)
        with sqlite3.connect(str(dest)) as chk:
            checked(chk.execute('pragma quick_check').fetchone()[0]=='ok','S03_BACKUP')
        result['s03_backup']={'bytes':dest.stat().st_size,'sha256':sha(dest)}
        save(path,result)
        # Stop only NOX Supervisor programs, never platform, SSH or Supervisor itself.
        order=[x for x in FIRST if before.get(x) in ('RUNNING','STARTING')]
        order += sorted(k for k,v in before.items() if k.startswith('nox-')
                and k not in FIRST and v in ('RUNNING','STARTING'))
        for name in order:
            try:
                rc,out=invoke(['supervisorctl','stop',name],28)
                status=supervisor().get(name)
                if status in ('STOPPED','EXITED','FATAL'):result['stopped'].append(name)
                else:result['stop_failed'].append({'name':name,'state':status,'rc':rc})
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as e:
                result['stop_failed'].append({'name':name,'reason':type(e).__name__})
            save(path,result)
        for pid,start in chats:
            now=identity(pid)
            if now is None:continue
            if now[0]!=start:result['stop_failed'].append({'name':'detached_chat','reason':'PID_CHANGED'});continue
            os.kill(pid,signal.SIGTERM)
            for _ in range(50):
                row=identity(pid)
                if row is None or row[0]!=start:break
                time.sleep(.2)
            else:result['stop_failed'].append({'name':'detached_chat','reason':'SIGTERM_TIMEOUT'})
        after=supervisor()
        result['supervisor_after']={k:v for k,v in after.items() if k.startswith('nox-')}
        result['old_chat_after']=[p for p,_ in oldchat()]
        stopped=not result['stop_failed'] and not result['old_chat_after'] and all(
                v not in ('RUNNING','STARTING') for k,v in after.items() if k.startswith('nox-'))
        result['stop_verified']=stopped
        save(path,result)
        if not stopped:
            result['state']='HOLD_STOP_INCOMPLETE_NO_DELETE';save(path,result)
            print(PREFIX+json.dumps({'kind':'nox_emergency_model_reset','data':result}),flush=True)
            return 2
        in_use=no_open()
        checked(in_use is not None,'OPEN_FILE_SCAN')
        free0=os.statvfs(ROOT);before_bytes=free0.f_bavail*free0.f_frsize
        # No wildcard; reject symlinks, unexpected sizes, hardlinks, in-use inodes and changed hashes.
        for name,size in OLD.items():
            p=Path(name)
            try:
                checked(p.is_absolute() and name.startswith('/root/nox/'),'DELETE_SCOPE')
                checked(not any(x.is_symlink() for x in (p,*p.parents)),'DELETE_SYMLINK')
                if not p.exists():result['deletion_holds'].append([name,'ABSENT']);continue
                st=p.stat(follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or st.st_size!=size or st.st_nlink!=1 or st.st_uid!=0:
                    result['deletion_holds'].append([name,'FILE_IDENTITY_CHANGED']);continue
                if (st.st_dev,st.st_ino) in in_use:
                    result['deletion_holds'].append([name,'OPEN_FILE_OR_MMAP']);continue
                digest=sha(p);new=p.stat(follow_symlinks=False)
                if (new.st_dev,new.st_ino,new.st_size,new.st_ctime_ns,new.st_mtime_ns)!=(st.st_dev,st.st_ino,st.st_size,st.st_ctime_ns,st.st_mtime_ns):
                    result['deletion_holds'].append([name,'HASH_READ_RACE']);continue
                p.unlink();result['deleted'].append({'path':name,'bytes':size,'sha256':digest})
                save(path,result)
            except (OSError,RuntimeError) as e:result['deletion_holds'].append([name,type(e).__name__])
        for name in ALIASES:
            p=Path(name)
            if p.is_symlink():
                target=os.path.abspath(str(p.parent/os.readlink(p)))
                if target.startswith('/root/nox/'):
                    p.unlink();result['aliases_removed'].append(name)
        os.sync()
        free1=os.statvfs(ROOT)
        result['bytes_reclaimed_verified']=max(0,free1.f_bavail*free1.f_frsize-before_bytes)
        result['free_after_bytes']=free1.f_bavail*free1.f_frsize
        result['state']='MODEL_UPDATE_STOP_DONE_EXACT_OLD_GGUF_CLEANUP'
        save(path,result)
        print(PREFIX+json.dumps({'kind':'nox_emergency_model_reset','data':result}),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
        return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:
        print(PREFIX+json.dumps({'kind':'nox_emergency_model_reset','state':'HOLD','reason':str(e)[:130]}),flush=True)
        raise SystemExit(2)
