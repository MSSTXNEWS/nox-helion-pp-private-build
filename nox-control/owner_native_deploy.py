#!/usr/bin/env python3
"""Read-only private backup capability probe. No profile creation/copy/resume/delete."""
import sys
sys.dont_write_bytecode = True
import configparser, datetime, fcntl, hashlib, json, os, re, selectors, shutil, signal, socket, stat, subprocess, time
from pathlib import Path, PureWindowsPath

ROOT = Path('/root/nox')
STATE = ROOT/'state'
FLAGS = (ROOT/'STOP', STATE/'OWNER_MAINTENANCE.flag', STATE/'TRAIN_HOLD.flag', STATE/'TRAIN_PAUSE_REQUEST.flag')
KNOWN = (STATE/'cold_drive.conf', Path('/root/.config/rclone/rclone.conf'), ROOT/'rclone.conf', STATE/'cold_pc.conf')
SAFE_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
DEADLINE = None

class Hold(RuntimeError): pass
def require(value, code):
    if not value: raise Hold('HOLD_CAPABILITY_'+code)
def remaining(limit):
    left = limit if DEADLINE is None else DEADLINE-time.monotonic()
    require(left > 0, 'DEADLINE')
    return max(.1,min(limit,left))
def identity(s): return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def plain(path):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH')
    require(not any(p.is_symlink() for p in (path,*path.parents)), 'SYMLINK')
    return path
def read_regular(path, private=False, maximum=131072):
    path=plain(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid() and before.st_size<=maximum, 'FILE_SCOPE')
        require(stat.S_IMODE(before.st_mode)==0o600 if private else not before.st_mode&0o022, 'FILE_MODE')
        data=os.read(fd,maximum+1)
        require(len(data)==before.st_size and identity(before)==identity(os.fstat(fd))==identity(path.lstat()), 'FILE_CHANGED')
        return data
    finally: os.close(fd)
def flags():
    require(all(p.is_file() for p in FLAGS), 'FOUR_STOP_FLAGS_REQUIRED')
    return [hashlib.sha256(read_regular(p)).hexdigest() for p in FLAGS]
def execute(argv, seconds=12, pass_fds=(), collect=False):
    # Bounded pipe, no provider diagnostics or filenames reach logs; kill whole subprocess group.
    env={'PATH':SAFE_PATH,'LC_ALL':'C','HOME':'/root'}
    end=time.monotonic()+remaining(seconds)
    p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if collect else subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,env=env,pass_fds=pass_fds,start_new_session=True)
    out=bytearray();sel=selectors.DefaultSelector()
    if collect: sel.register(p.stdout,selectors.EVENT_READ)
    try:
        while p.poll() is None or collect and sel.get_map():
            require(time.monotonic()<end,'COMMAND_TIMEOUT')
            if collect:
                for key,_ in sel.select(.05):
                    chunk=os.read(key.fd,8192)
                    if not chunk:sel.unregister(key.fileobj)
                    else:out.extend(chunk);require(len(out)<=131072,'OUTPUT_BOUND')
            else:time.sleep(.03)
        return p.returncode,bytes(out)
    finally:
        sel.close()
        if p.poll() is None:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        p.wait(timeout=3)
        if p.stdout:p.stdout.close()
def binary(name):
    p=shutil.which(name,path=SAFE_PATH);require(p is not None,'EXECUTABLE_UNAVAILABLE');return p
def stopped():
    rc,raw=execute([binary('supervisorctl'),'status'],12,collect=True)
    rows=[line.split() for line in raw.decode('utf8','replace').splitlines() if line.startswith('nox-')]
    require(rc in (0,3) and bool(rows) and all(len(x)>1 and x[1] in ('STOPPED','EXITED','FATAL') for x in rows),'SERVICES_NOT_STOPPED')
    return len(rows)
def custom_paths():
    result=[]
    for key in ('NOX_RCLONE_CONFIG','RCLONE_CONFIG'):
        if os.environ.get(key):result.append(('current_'+key,os.environ[key]))
    # Only extract the two named path settings, never expose the process environment.
    try:
        fd=os.open('/proc/1/environ',os.O_RDONLY|os.O_NOFOLLOW)
        try:raw=os.read(fd,131073)
        finally:os.close(fd)
        require(len(raw)<=131072,'ENV_BOUND')
        for item in raw.split(b'\0'):
            key,sep,val=item.partition(b'=')
            if sep and key in (b'NOX_RCLONE_CONFIG',b'RCLONE_CONFIG'):
                result.append(('init_'+key.decode(),val.decode('utf8','strict')))
    except (OSError,UnicodeError,Hold):pass
    return result
def pc_metadata(path=None,now=None):
    path=path or STATE/'pc_shell/connection.json';now=time.time() if now is None else now
    row={'present':path.exists(),'private_metadata':False,'identity_valid':False,'fresh':False,'connected_claim':False,'loopback_open':False,'authenticated_read':False}
    if not row['present']:return row,None
    try:
        data=json.loads(read_regular(path,True,32000));row['private_metadata']=True
        valid=data.get('schema')=='NOX_PC_LINK_V1' and data.get('instance_id')==60509551 and data.get('reverse_host')=='127.0.0.1' and data.get('reverse_port')==46051
        row['identity_valid']=valid;row['connected_claim']=data.get('connected') is True
        stamp=data.get('last_verified_utc')
        if isinstance(stamp,str):
            dt=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if dt.tzinfo is not None:row['fresh']=-5<=now-dt.timestamp()<=150
        root=data.get('backup_root','');win=PureWindowsPath(root) if isinstance(root,str) else PureWindowsPath('')
        target='nox_pc:/'+win.as_posix().rstrip('/') if win.is_absolute() and re.fullmatch('[A-Za-z]:',win.drive) and '..' not in win.parts and not any(ord(c)<32 or c in '?*<>|"#' for c in root) else None
        if valid and row['connected_claim'] and target:
            try:
                with socket.create_connection(('127.0.0.1',46051),timeout=remaining(2)):row['loopback_open']=True
            except OSError:pass
        return row,target if valid else None
    except (OSError,ValueError,TypeError,Hold):row['state']='HOLD_PC_METADATA';return row,None
def pc_profile_valid(config):
    if not config.has_section('nox_pc'):return False
    s=config['nox_pc'];folder=STATE/'pc_shell'
    expected={'type':'sftp','host':'127.0.0.1','port':'46051','key_file':str(folder/'operator_ed25519'),'known_hosts_file':str(folder/'rclone_known_hosts'),'shell_type':'none'}
    if any(s.get(k)!=v for k,v in expected.items()):return False
    if s.get('ssh') or s.get('ssh_command'):return False
    read_regular(folder/'operator_ed25519',True,16384)
    read_regular(folder/'rclone_known_hosts',False,16384)
    return True
def probe_profile(label,path,pc,target):
    row={'candidate':label,'present':False,'private_metadata':False,'nox_drive':False,'nox_pc':False,'drive_authenticated_read':False,'pc_authenticated_read':False,'source_unchanged':True}
    try:
        require(isinstance(path,(str,Path)) and len(str(path))<=4096 and not any(ord(c)<32 for c in str(path)),'PATH')
        path=plain(path);row['present']=path.exists()
        if not row['present']:return row
        raw=read_regular(path,True);before=identity(path.lstat());row['private_metadata']=True
        config=configparser.ConfigParser(interpolation=None);config.read_string(raw.decode('utf8'))
        row['nox_drive']=config.has_section('nox_drive');row['nox_pc']=config.has_section('nox_pc')
        # A volatile memory copy prevents rclone OAuth refresh from changing source config.
        fd=os.memfd_create('nox-capability-profile',os.MFD_CLOEXEC)
        try:
            os.write(fd,raw);os.lseek(fd,0,os.SEEK_SET)
            cmd=[binary('rclone'),'--config','/proc/self/fd/'+str(fd),'--retries','1','--low-level-retries','1','--contimeout','3s','--timeout','8s','--max-duration','10s']
            if row['nox_drive']:
                rc,_=execute(cmd+['lsf','nox_drive:NOX_PRIVATE_BACKUPS','--max-depth','1','--dirs-only'],12,(fd,))
                row['drive_authenticated_read']=rc==0
            if row['nox_pc'] and pc['identity_valid'] and pc['connected_claim'] and pc['loopback_open'] and target and pc_profile_valid(config):
                rc,_=execute(cmd+['lsf',target,'--max-depth','1','--dirs-only'],12,(fd,))
                row['pc_authenticated_read']=rc==0
        finally:os.close(fd)
        row['source_unchanged']=identity(path.lstat())==before and read_regular(path,True)==raw
        require(row['source_unchanged'],'PROFILE_CHANGED')
    except (OSError,ValueError,configparser.Error,Hold,subprocess.SubprocessError):row['state']='HOLD_PROFILE_PROBE'
    return row
def main():
    global DEADLINE
    DEADLINE=time.monotonic()+110
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');sha=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch('[0-9]{1,24}',request) and re.fullmatch('[a-f0-9]{40}',sha),'OWNER_CONTEXT')
    before=flags();count=stopped();lockpath=plain(STATE/'owner_maintenance.lock')
    # Existing lease only: no O_CREAT, mkdir, profile write, snapshot or transfer.
    lock=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(lock);require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid(),'LEASE_FILE')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Hold('HOLD_CAPABILITY_LEASE_BUSY') from None
        require(flags()==before,'FLAGS_CHANGED');stopped()
        pc,target=pc_metadata();custom=custom_paths();seen=set();rows=[]
        for label,path in custom+[(f'known_{i}',p) for i,p in enumerate(KNOWN)]:
            if str(path) in seen:continue
            seen.add(str(path))
            if DEADLINE-time.monotonic()<30:
                rows.append({'candidate':label,'state':'NOT_PROBED_BUDGET','drive_authenticated_read':False,'pc_authenticated_read':False})
                continue
            rows.append(probe_profile(label,path,pc,target))
        pc['authenticated_read']=any(r['pc_authenticated_read'] for r in rows)
        require(flags()==before,'FLAGS_CHANGED');stopped()
        return {'schema':'NOX_PRIVATE_CAPABILITY_V2','instance':60509551,'request':request,'source_sha':sha,
                'task_ids':['2V14-04','2V14-07'],'custom_env_candidates':len(custom),'profiles':rows,'pc':pc,
                'state':'EXISTING_PRIVATE_READ_ROUTE_OBSERVED' if any(r['drive_authenticated_read'] or r['pc_authenticated_read'] for r in rows) else 'HOLD_CAPABILITY_INCOMPLETE' if any(r.get('state')=='NOT_PROBED_BUDGET' for r in rows) else 'HOLD_NO_PRIVATE_READ_ROUTE_OBSERVED',
                'stopped_services':count,'stop_flags_unchanged':True,'source_writes':0,'uploaded_bytes':0,'source_deleted':False,'resume_attempted':False,
                'external_copy_verified':False,'write_permission_verified':False,'restore_verified':False,'cloudcopy':'SEPARATE_PROVIDER_METADATA_ONLY'}
    finally:os.close(lock)
if __name__=='__main__':
    try:
        print('NOX_MAINT_CAPABILITY='+json.dumps(main(),sort_keys=True),flush=True)
        print('NOX_MAINT_DEPLOY_COMPLETE=true',flush=True)
    except Exception as exc:
        code=str(exc) if isinstance(exc,Hold) else 'HOLD_CAPABILITY_UNEXPECTED'
        print('NOX_MAINT_CAPABILITY='+json.dumps({'state':code,'source_writes':0,'uploaded_bytes':0,'source_deleted':False,'resume_attempted':False}),flush=True)
        raise SystemExit(2)
