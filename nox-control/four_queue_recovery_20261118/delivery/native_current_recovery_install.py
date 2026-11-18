"""Scoped owner repair: three current four-queue files and one real health leaf.

File ownership/FD-CAS derives from the accepted post8098 headroom transaction;
the bounded supervisor and native-readback flow derives from four-queue32546.
No second dispatcher, lock, queue, model endpoint or maintenance entry is added.
The build wrapper injects the reviewed pure composer and exact source bytes.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time

ROOT = Path('/root/nox')
OWNER_UID = 0
OWNER_GID = 0
SERVICE = 'nox-dispatcher-t855u'
LOCK_PIN = {'dev':36, 'ino':59886214}
DIRECTOR_PIN = {'pid':3680815, 'start_ticks':175371075}
PREVIOUS_WORKERS = {3680900:175371710,3680901:175371710,3680902:175371710}
MAIN_SOURCE = 'scripts/nox_dispatcher_t855u.py'
MAIN_SHA = '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21'
PROTECTED = {'chat':{'pid':3266857,'start_ticks':172046662},
    'proxy':{'pid':3703386,'start_ticks':175609570},
    'web':{'pid':3505392,'start_ticks':173653097}}
MAX_SECONDS = 240
MAX_FILE = 16*1024*1024
STATE = 'state/dispatcher/state.json'
STATUS = 'status/agents_t856u.json'
ATTEMPT_PREFIX = 'four_queue_recovery_'
COMPOSER = None
DISPATCHER_SOURCE = None


class Hold(Exception):
    pass


def require(value, reason):
    if not value:
        raise Hold('HOLD_FOUR_QUEUE_RECOVERY_' + reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def fingerprint(info):
    return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_mode','st_uid',
        'st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))


def directory_identity(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid)


def metadata(info):
    return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
        'mode':stat.S_IMODE(info.st_mode),'bytes':info.st_size,'mtime_ns':info.st_mtime_ns}


def process_identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    try:
        fields = Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()
        if fields[0] not in ('R','S','D','I'):
            return None
        return {'pid':pid,'start_ticks':int(fields[19]),'ppid':int(fields[1]),'pgrp':int(fields[2])}
    except (OSError,ValueError,IndexError):
        return None


def argv_digest(pid):
    with Path('/proc',str(pid),'cmdline').open('rb') as handle:
        raw = handle.read(8193)
    require(0 < len(raw) <= 8192, 'DIRECTOR_ARGV_BOUND')
    return digest(raw)


def lifetime_present(pid,start_ticks):
    """STOPPED/Z/unknown states are never silently classified as disappearance."""
    try:
        with Path('/proc',str(pid),'stat').open('rb') as stream:
            raw = stream.read(8193)
        require(0 < len(raw) <= 8192,'LIFETIME_STAT_BOUND')
        fields = raw.rsplit(b') ',1)[1].split()
        return int(fields[19]) == start_ticks
    except FileNotFoundError:
        return False
    except (OSError,ValueError,IndexError):
        raise Hold('HOLD_FOUR_QUEUE_RECOVERY_LIFETIME_UNKNOWN') from None


def supervisor(action):
    require(action in ('status','stop','start'), 'SUPERVISOR_ACTION')
    value = subprocess.run(['supervisorctl',action,SERVICE], capture_output=True,
                           text=True,timeout=25)
    if action == 'status':
        match = re.fullmatch(re.escape(SERVICE)+r'\s+(RUNNING|STOPPED|STARTING|STOPPING|BACKOFF|FATAL|EXITED)\b(?:\s+pid\s+(\d+))?.*',
                             value.stdout.strip())
        require(match is not None,'SERVICE_STATUS')
        return {'state':match[1],'pid':int(match[2]) if match[2] else None}
    return {'returncode':value.returncode}  # No retry based on an ACK alone.


class Installer:
    def __init__(self, request, source):
        require(isinstance(request,str) and re.fullmatch(r'[0-9]{1,24}',request)
            and isinstance(source,str) and re.fullmatch(r'[a-f0-9]{40}',source),'OWNER_CONTEXT')
        require(os.geteuid() == OWNER_UID,'OWNER_UID')
        self.request,self.source = request,source
        self.deadline = time.monotonic()+MAX_SECONDS
        self.fds,self.edges,self.parents = [],[],{}
        self.state_fd = self.lock_fd = self.attempt_fd = None
        self.lease_held = self.released = self.prior_attempt = False
        self.phase = 'NEW'
        self.before,self.after,self.staged,self.installed = {},{},{},{}
        self.replace_attempts,self.rollback_attempts = [],[]
        self.old_director = self.new_director = self.restored_director = None
        self.old_argv = None
        self.old_workers = []
        self.inert_tracks = {}
        self.native_catalog_ids = []
        self.stop_attempted = self.stopped = self.start_attempted = False
        self.queue_before = None
        self.accepted = False
        self.attempt_name = ATTEMPT_PREFIX+request
        self.sequence = 0

    def check(self):
        require(time.monotonic() <= self.deadline,'DEADLINE')

    def directory(self,path):
        path = Path(path)
        require(path.is_absolute() and '..' not in path.parts,'DIRECTORY_SCOPE')
        flags = os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
        parent = os.open('/',flags); self.fds.append(parent)
        for part in path.parts[1:]:
            self.check()
            child = os.open(part,flags,dir_fd=parent); self.fds.append(child)
            info = os.fstat(child)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,OWNER_UID),'DIRECTORY_OWNER')
            self.edges.append((parent,part,child,directory_identity(info)))
            parent = child
        return parent

    def guard(self, *, lease=True, stop=True):
        self.check()
        for parent,name,child,expected in self.edges:
            require(directory_identity(os.fstat(child)) == expected ==
                directory_identity(os.stat(name,dir_fd=parent,follow_symlinks=False)),'DIRECTORY_DRIFT')
        require(self.lock_fd is not None,'LEASE_MISSING')
        opened = os.fstat(self.lock_fd)
        named = os.stat('owner_maintenance.lock',dir_fd=self.state_fd,follow_symlinks=False)
        require(stat.S_ISREG(opened.st_mode) and opened.st_uid == OWNER_UID and opened.st_nlink == 1
            and not opened.st_mode & 0o022 and directory_identity(opened) == directory_identity(named)
            and {'dev':opened.st_dev,'ino':opened.st_ino} == LOCK_PIN,'LEASE_IDENTITY')
        if lease:
            require(self.lease_held and not self.released,'LEASE_PHASE')
            fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if stop:
            names = ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP',
                     'state/STOP.flag','state/OWNER_MAINTENANCE.flag')
            require(not any(p.exists() or p.is_symlink() for p in
                [*(ROOT/name for name in names),Path('/workspace/NOX_STOP')]),'OWNER_STOP')
        for label,expected in PROTECTED.items():
            actual = process_identity(expected['pid'])
            require(actual is not None and actual['start_ticks'] == expected['start_ticks'],
                    'PROTECTED_'+label.upper())

    def acquire(self):
        self.state_fd = self.directory(ROOT/'state')
        self.lock_fd = os.open('owner_maintenance.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,
                              dir_fd=self.state_fd)
        self.fds.append(self.lock_fd)
        fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.lease_held = True
        self.guard()

    def path(self,relative):
        require(isinstance(relative,str) and not relative.startswith('/') and '..' not in Path(relative).parts,'FILE_SCOPE')
        parent,name = relative.rsplit('/',1)
        if parent not in self.parents:
            self.parents[parent] = self.directory(ROOT/parent)
        return self.parents[parent],name

    def read(self,parent,name,maximum=MAX_FILE):
        require('/' not in name and name not in ('','.','..'),'FILE_NAME')
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == OWNER_UID and info.st_nlink == 1
                    and 0 < info.st_size <= maximum,'FILE_OWNER_BOUND')
            raw = os.pread(fd,maximum+1,0)
            require(len(raw) == info.st_size and fingerprint(info) == fingerprint(os.fstat(fd))
                == fingerprint(os.stat(name,dir_fd=parent,follow_symlinks=False)),'FILE_DRIFT')
            self.check()
            return raw,info
        finally:
            os.close(fd)

    def read_path(self,relative,maximum=MAX_FILE):
        return self.read(*self.path(relative),maximum=maximum)

    def write_new(self,parent,name,raw,mode,uid=None,gid=None, *, lease=True):
        self.guard(lease=lease)
        uid = OWNER_UID if uid is None else uid
        gid = OWNER_GID if gid is None else gid
        require('/' not in name and 0 < len(raw) <= MAX_FILE,'WRITE_SCOPE')
        fd = os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
        try:
            view = memoryview(raw)
            while view:
                self.check(); count = os.write(fd,view)
                require(count > 0,'SHORT_WRITE'); view = view[count:]
            os.fchown(fd,uid,gid); os.fchmod(fd,mode); os.fsync(fd)
        finally:
            os.close(fd)
        actual,info = self.read(parent,name)
        require(actual == raw and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)) == (uid,gid,mode),'WRITE_READBACK')
        os.fsync(parent)
        return info

    def record(self,phase,fields=None):
        require(self.attempt_fd is not None,'ATTEMPT_MISSING')
        self.sequence += 1
        value = {'schema':'NOX_CURRENT_FOUR_QUEUE_RECOVERY_INSTALL_V1','request':self.request,
            'source_sha':self.source,'phase':phase,**(fields or {})}
        self.write_new(self.attempt_fd,f'{self.sequence:02d}_{phase}.json',encoded(value),0o600,
                       lease=not self.released)

    def begin(self):
        try:
            os.stat(self.attempt_name,dir_fd=self.state_fd,follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            self.prior_attempt = True
            raise Hold('HOLD_FOUR_QUEUE_RECOVERY_PRIOR_ATTEMPT_RECONCILE')
        os.mkdir(self.attempt_name,0o700,dir_fd=self.state_fd)
        self.attempt_fd = os.open(self.attempt_name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                  dir_fd=self.state_fd)
        self.fds.append(self.attempt_fd)
        info = os.fstat(self.attempt_fd)
        require(info.st_uid == OWNER_UID and stat.S_IMODE(info.st_mode) == 0o700,'ATTEMPT_PRIVATE')
        self.edges.append((self.state_fd,self.attempt_name,self.attempt_fd,directory_identity(info)))
        os.fsync(self.state_fd)

    def exact_before(self,relative):
        raw,info = self.read_path(relative)
        expected,old = self.before[relative]
        require(raw == expected and fingerprint(info) == fingerprint(old),'PREIMAGE_CAS')
        return info

    def owned_after(self,relative):
        raw,info = self.read_path(relative)
        stage = self.staged[relative]
        old = self.before[relative][1]
        require((info.st_dev,info.st_ino) == (stage.st_dev,stage.st_ino) and raw == self.after[relative]
            and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)) ==
                (old.st_uid,old.st_gid,stat.S_IMODE(old.st_mode)),'OWNED_POSTIMAGE_CAS')
        return info

    def stage_file(self,relative,index):
        self.guard(); self.exact_before(relative)
        parent,name = self.path(relative)
        raw,old = self.before[relative]
        backup = f'original_{index}.bin'
        self.write_new(self.attempt_fd,backup,raw,0o600)
        stage_name = f'.nox-recovery-{self.request}-{index}.stage'
        self.staged[relative] = self.write_new(parent,stage_name,self.after[relative],stat.S_IMODE(old.st_mode),old.st_uid,old.st_gid)
        self.record('STAGED',{'path':relative,'stage_identity':metadata(self.staged[relative]),
            'before_sha256':digest(raw),'after_sha256':digest(self.after[relative])})

    def install_file(self,relative,index):
        self.guard(); self.exact_before(relative)
        parent,name = self.path(relative)
        raw,old = self.before[relative]
        require(relative in self.staged,'STAGE_REQUIRED_BEFORE_STOP')
        stage_name = f'.nox-recovery-{self.request}-{index}.stage'
        self.record('REPLACE_INTENT',{'path':relative,'before':metadata(old),'before_sha256':digest(raw),
            'stage_identity':metadata(self.staged[relative]),'after_sha256':digest(self.after[relative])})
        self.guard(); self.exact_before(relative)
        staged,info = self.read(parent,stage_name)
        require(staged == self.after[relative] and fingerprint(info) == fingerprint(self.staged[relative]),'STAGE_CAS')
        self.replace_attempts.append(relative)
        os.replace(stage_name,name,src_dir_fd=parent,dst_dir_fd=parent)
        os.fsync(parent)
        self.installed[relative] = metadata(self.owned_after(relative))

    def rollback_files(self):
        require(not self.released,'ROLLBACK_AFTER_ADMISSION_FORBIDDEN')
        # Validate the whole affected set before restoring even its first file.
        owned = []
        for relative in self.replace_attempts:
            raw,info = self.read_path(relative)
            if raw == self.before[relative][0] and fingerprint(info) == fingerprint(self.before[relative][1]):
                continue  # Proven rename did not happen.
            self.owned_after(relative); owned.append(relative)
        for relative in reversed(owned):
            self.guard(); self.owned_after(relative)
            index = list(self.after).index(relative)
            raw,info = self.read(self.attempt_fd,f'original_{index}.bin')
            old = self.before[relative][1]
            require(raw == self.before[relative][0] and stat.S_IMODE(info.st_mode) == 0o600,'BACKUP_CAS')
            parent,name = self.path(relative)
            restore = f'.nox-recovery-{self.request}-{index}.restore'
            restored = self.write_new(parent,restore,raw,stat.S_IMODE(old.st_mode),old.st_uid,old.st_gid)
            self.record('ROLLBACK_INTENT',{'path':relative,'restore_identity':metadata(restored)})
            self.guard(); self.owned_after(relative)
            staged,check = self.read(parent,restore)
            require(staged == raw and fingerprint(check) == fingerprint(restored),'ROLLBACK_STAGE_CAS')
            self.rollback_attempts.append(relative)
            os.replace(restore,name,src_dir_fd=parent,dst_dir_fd=parent); os.fsync(parent)
            actual,info = self.read_path(relative)
            require(actual == raw and (info.st_dev,info.st_ino) == (restored.st_dev,restored.st_ino),'ROLLBACK_READBACK')
        return owned

    def queue(self):
        value = json.loads(self.read_path(STATE)[0])
        require(isinstance(value,dict) and isinstance(value.get('tasks'),dict)
                and len(value['tasks']) <= 20000,'QUEUE_SCHEMA')
        require(all(isinstance(row,dict) for row in value['tasks'].values()),'QUEUE_ROW_SCHEMA')
        return value

    def running_effects(self,state):
        """The exact9ae track handler is a constant wait, never an executor.

        Preserve its claim/result. Exact9ae startup quarantines residual
        running rows as BLOCKED; this installer does not reset or replay them.
        Every other running handler remains a blocker.
        """
        require(digest(self.read_path(MAIN_SOURCE,262144)[0]) == MAIN_SHA,'TRACK_MAIN_SOURCE')
        active,inert = [],{}
        for task_id,row in state['tasks'].items():
            if row.get('status') != 'running':
                continue
            claim = row.get('owner_claim')
            pid = claim.get('pid') if isinstance(claim,dict) else None
            owned_or_dead = (type(pid) is int and pid > 1 and
                (pid == self.old_director['pid'] or not Path('/proc',str(pid)).exists()))
            if (row.get('handler') == 'track' and task_id not in self.native_catalog_ids
                    and isinstance(claim,dict) and owned_or_dead
                    and re.fullmatch(r'[a-f0-9]{24}',str(claim.get('nonce','')))):
                inert[task_id] = row
            else:
                active.append(task_id)
        return active,inert

    def zero_pool_proof(self,state,observed):
        require(observed.get('workers') == [] and len(self.native_catalog_ids) == 7
            and all(state['tasks'].get(key,{}).get('status') == 'done' for key in self.native_catalog_ids),
            'EMPTY_POOL_NOT_SETTLED')
        # Accepted old pool identities, not an inference from an empty UI list.
        until = time.monotonic()+5
        while True:
            self.guard(); self.service_is(self.old_director)
            alive = [pid for pid,start in PREVIOUS_WORKERS.items() if lifetime_present(pid,start)]
            if not alive:
                return
            require(time.monotonic() < until,'EMPTY_STATUS_OLD_WORKER_STILL_ALIVE')
            time.sleep(.1)

    def native_status(self):
        value = json.loads(self.read_path(STATUS,2*1024*1024)[0])
        result = value.get('native_subexecutors') if isinstance(value,dict) else None
        require(isinstance(result,dict),'NATIVE_STATUS')
        return result

    def service_is(self,expected):
        value = supervisor('status')
        actual = process_identity(value['pid'])
        require(value['state'] == 'RUNNING' and actual is not None
            and actual['pid'] == expected['pid'] and actual['start_ticks'] == expected['start_ticks'],
            'SERVICE_LIFETIME')
        return actual

    def stop_service(self,expected, *, original=False):
        self.guard(); self.service_is(expected)
        require(argv_digest(expected['pid']) == self.old_argv,'SERVICE_ARGV_DRIFT')
        self.record('STOP_INTENT',{'lifetime':expected,'original':original})
        if original:
            self.stop_attempted = True
        try:
            supervisor('stop')
        except (OSError,subprocess.SubprocessError):
            pass
        until = time.monotonic()+15
        while True:
            self.guard()
            value = supervisor('status')
            require(not (value['state'] == 'RUNNING' and value['pid'] != expected['pid']),
                    'FOREIGN_SERVICE_PRESERVED')
            old_alive = lifetime_present(expected['pid'],expected['start_ticks'])
            children_gone = not original or all(not lifetime_present(row['pid'],row['process_starttime'])
                                                for row in self.old_workers)
            if value['state'] in ('STOPPED','FATAL','EXITED') and not old_alive and children_gone:
                break
            require(time.monotonic() < until,'STOP_OUTCOME_UNKNOWN')
            time.sleep(.25)
        if original:
            self.stopped = True

    def start_service(self, *, restored=False):
        self.guard()
        value = supervisor('status')
        require(value['state'] in ('STOPPED','FATAL','EXITED'),'START_REQUIRES_STOPPED')
        self.record('START_INTENT',{'restored_original_sources':restored})
        if not restored:
            self.start_attempted = True
        try:
            supervisor('start')
        except (OSError,subprocess.SubprocessError):
            pass
        until,stable,since = time.monotonic()+25,None,None
        while time.monotonic() < until:
            self.guard()
            value = supervisor('status')
            actual = process_identity(value['pid'])
            if value['state'] == 'RUNNING' and actual is not None:
                require(actual['ppid'] == self.old_director['ppid'] and
                    (actual['pid'],actual['start_ticks']) != (self.old_director['pid'],self.old_director['start_ticks'])
                    and argv_digest(actual['pid']) == self.old_argv,'NEW_DIRECTOR_BINDING')
                if restored:
                    require(self.restored_director in (None,actual),'RESTORE_LIFETIME_DRIFT')
                    self.restored_director = actual
                else:
                    require(self.new_director in (None,actual),'NEW_DIRECTOR_LIFETIME_DRIFT')
                    if self.new_director is None:
                        self.new_director = actual
                        self.record('NEW_DIRECTOR_BOUND',{'lifetime':actual})
                loaded = restored
                if not restored:
                    try:
                        observed = self.native_status()
                        owner = observed.get('director') or {}
                        loaded = (owner.get('pid') == actual['pid'] and
                            owner.get('process_starttime') == actual['start_ticks'] and
                            type(observed.get('observed_at')) in (int,float) and
                            0 <= time.time()-observed['observed_at'] <= 15 and
                            observed.get('mode') == 'NORMAL' and observed.get('target') == 3)
                    except (Hold,OSError,ValueError,TypeError):
                        loaded = False
                if loaded:
                    if stable != actual:
                        stable,since = actual,time.monotonic()
                    elif time.monotonic()-since >= 2:
                        return actual
            elif value['state'] in ('FATAL','EXITED'):
                break
            time.sleep(.25)
        raise Hold('HOLD_FOUR_QUEUE_RECOVERY_STARTUP_NOT_VERIFIED')

    def rollback_before_release(self):
        require(not self.released,'ROLLBACK_AFTER_ADMISSION_FORBIDDEN')
        self.guard()
        require(COMPOSER.NEXT_TASK_ID not in self.queue()['tasks'],'NEW_CLAIM_PRESERVED_NO_ROLLBACK')
        if self.start_attempted:
            require(self.new_director is not None,'START_OUTCOME_UNKNOWN_NO_STOP')
            self.stop_service(self.new_director)
        else:
            require(self.stopped and supervisor('status')['state'] in ('STOPPED','FATAL','EXITED'),
                    'UNOWNED_STOPPED_STATE')
        restored = self.rollback_files()
        for name,(raw,_) in self.before.items():
            require(self.read_path(name)[0] == raw,'RESTORED_SOURCE_SET')
        self.start_service(restored=True)
        self.record('ROLLED_BACK',{'restored_files':restored,'director':self.restored_director,
            'previous_worker_pids_restored':False,'initial_pool_requires_real_work':True})
        self.phase = 'SOURCES_RESTORED_SERVICE_RUNNING'

    def prepare(self):
        require(COMPOSER is not None and isinstance(DISPATCHER_SOURCE,bytes),'EMBEDDED_SOURCES')
        self.acquire()
        for name,pin in COMPOSER.BEFORE.items():
            raw,info = self.read_path(name,262144)
            require(digest(raw) == pin and not info.st_mode & 0o022 and
                (stat.S_IMODE(info.st_mode) == 0o600 if name.endswith('.json') else
                 stat.S_IMODE(info.st_mode) == 0o644),'CURRENT_SOURCE_PREIMAGE')
            self.before[name] = (raw,info)
        for name,pin in COMPOSER.UNCHANGED.items():
            require(digest(self.read_path(name,262144)[0]) == pin,'UNCHANGED_CURRENT_SOURCE')
        # Preserve the actual current chat installation without reading any history.
        for name,pin in {
            'scripts/chat_proxy.py':'1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62',
            'scripts/common.py':'618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
        }.items():
            require(digest(self.read_path(name,262144)[0]) == pin,'PROTECTED_CHAT_SOURCE')
        self.after,composition = COMPOSER.prepare_change_set(
            {name:row[0] for name,row in self.before.items()},DISPATCHER_SOURCE,
            request_id=self.request,source_commit=self.source)
        self.native_catalog_ids = [row['id'] for row in json.loads(self.before[COMPOSER.CONFIG][0])['catalog']['tasks']]
        self.old_director = self.service_is(DIRECTOR_PIN)
        self.old_argv = argv_digest(self.old_director['pid'])
        until = time.monotonic()+35
        while True:
            self.guard()
            state = self.queue()
            require(COMPOSER.NEXT_TASK_ID not in state['tasks'],'NEW_TASK_ALREADY_EXISTS')
            active,_inert = self.running_effects(state)
            if not active:
                break
            require(time.monotonic() < until,'QUEUE_NOT_IDLE')
            time.sleep(.5)
        observed = self.native_status()
        require(observed.get('director',{}).get('pid') == self.old_director['pid'] and
            observed.get('director',{}).get('process_starttime') == self.old_director['start_ticks'] and
            type(observed.get('observed_at')) in (int,float) and 0 <= time.time()-observed['observed_at'] <= 15,
            'OLD_NATIVE_DIRECTOR')
        rows = observed.get('workers')
        require(isinstance(rows,list) and len(rows) in (0,3),'OLD_POOL_SCOPE')
        if not rows:
            self.zero_pool_proof(state,observed)
        else:
            require(len({row['pid'] for row in rows}) == 3,'OLD_THREE_WORKERS')
        for row in rows:
            actual = process_identity(row.get('pid'))
            require(actual is not None and actual['start_ticks'] == row.get('process_starttime')
                and actual['ppid'] == self.old_director['pid'] and row.get('current_task') is None,
                'OLD_WORKER_BUSY_OR_UNKNOWN')
        self.old_workers = rows
        self.begin()
        self.record('INTENT',{'composition':composition,'before':{name:{'identity':metadata(info),
            'sha256':digest(raw)} for name,(raw,info) in self.before.items()},
            'director':self.old_director,'workers':rows})
        # Compile, compose, back up and stage all three files before downtime.
        for index,relative in enumerate(self.after):
            self.stage_file(relative,index)

    def install_sources(self):
        self.stop_service(self.old_director,original=True)
        self.queue_before = self.queue()
        active,self.inert_tracks = self.running_effects(self.queue_before)
        require(not active,'CLAIM_AFTER_STOP')
        require(COMPOSER.NEXT_TASK_ID not in self.queue_before['tasks'],'NEW_TASK_ALREADY_EXISTS')
        self.write_new(self.attempt_fd,'queue_before.json',encoded(self.queue_before),0o600)
        for index,relative in enumerate(self.after):
            self.install_file(relative,index)
        for name in self.after:
            self.installed[name] = metadata(self.owned_after(name))
        self.record('SOURCE_INSTALLED',{'files':self.installed})
        self.start_service()
        self.record('ADMISSION_RELEASE_INTENT',{'director':self.new_director,
            'native_source_postimages':{name:digest(raw) for name,raw in self.after.items()}})
        # Mark BEFORE unlock: a lost unlock ACK must never authorize rollback
        # over a health task that may already have acquired the shared lease.
        self.released = True
        self.lease_held = False
        fcntl.flock(self.lock_fd,fcntl.LOCK_UN)
        self.phase = 'SOURCE_INSTALLED_ACCEPTANCE_PENDING'

    def leaf_proof(self,state,workers):
        task = state['tasks'].get(COMPOSER.NEXT_TASK_ID)
        if not isinstance(task,dict) or task.get('status') != 'done':
            return None
        evidence = task.get('result') or {}
        receipt = evidence.get('receipt') or {}
        event = receipt.get('worker_result') or {}
        leaf = event.get('leaf_evidence') or {}
        worker = leaf.get('worker') or {}
        known = {(row['pid'],row['process_starttime']) for row in workers}
        require(receipt.get('task_id') == COMPOSER.NEXT_TASK_ID and receipt.get('claim') == task.get('owner_claim')
            and receipt.get('source_sha256') == COMPOSER.AFTER_DISPATCHER
            and receipt.get('phase') == 'NATIVE_LEAF_COMPLETED_ORIGINAL_NOT_ACCEPTED'
            and receipt.get('original_task_accepted') is False
            and receipt.get('parent_task_id') == '1V14-01' and receipt.get('queue_id') == 'Q1_RUNTIME_CHAT'
            and digest(encoded(receipt)) == evidence.get('receipt_sha256')
            and leaf.get('operation') == 'chat_health' and leaf.get('check_completed') is True
            and leaf.get('check_passed') is True and leaf.get('model_called') is False
            and leaf.get('original_task_accepted') is False
            and digest(encoded(leaf)) == event.get('leaf_evidence_sha256')
            and (worker.get('pid'),worker.get('process_starttime')) in known,'HEALTH_RECEIPT_PROOF')
        text = 'NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+digest(encoded(receipt))
        parent = self.directory(ROOT/'kb')
        fd = os.open('knowledge.sqlite',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == OWNER_UID,'S03_FILE_OWNER')
            conn = sqlite3.connect((ROOT/'kb/knowledge.sqlite').as_uri()+'?mode=ro',uri=True,timeout=.2)
            try:
                conn.execute('PRAGMA query_only=ON')
                deadline = time.monotonic()+2
                conn.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
                rows = conn.execute("SELECT id,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                                    (text,'owner_native_subagents')).fetchall()
            finally:
                conn.close()
            current = os.stat('knowledge.sqlite',dir_fd=parent,follow_symlinks=False)
            require((info.st_dev,info.st_ino) == (current.st_dev,current.st_ino),'S03_IDENTITY_DRIFT')
            require(len(rows) == 1 and rows[0][2] == digest(('M2|'+text).encode()) and
                    json.loads(rows[0][1]).get('receipt') == receipt,'S03_EXACT_RECEIPT')
        finally:
            os.close(fd)
        return {'task_id':task['id'],'receipt_sha256':digest(encoded(receipt)),
            's03_item_id':rows[0][0],'exact_s03_readback_verified':True,'worker':worker,
            'scope':'SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED','original_task_accepted':False,
            'check_passed':True,'model_called':False}

    def acceptance(self):
        until = time.monotonic()+75
        first = None
        while time.monotonic() < until:
            self.guard(lease=False)
            self.service_is(self.new_director)
            for name in self.after:
                self.owned_after(name)
            state = self.queue()
            original = self.queue_before['tasks']
            require(set(original) <= set(state['tasks']),'QUEUE_IDS_LOST')
            historical = {key:row for key,row in original.items() if row.get('status') in ('done','failed','blocked')}
            require(all(all(row.get(field) == state['tasks'][key].get(field) for field in
                    ('status','owner_claim','result')) for key,row in historical.items()),'HISTORICAL_RECEIPT_CHANGED')
            for key,prior in self.inert_tracks.items():
                current = state['tasks'][key]
                require(all(prior.get(field) == current.get(field) for field in
                    ('handler','params','owner_claim','result','retries')) and
                    current.get('status') == 'blocked' and current.get('note') ==
                    'HOLD: previous in-flight job requires child/process reconciliation before replay',
                    'INERT_TRACK_QUARANTINE_CHANGED')
            observed = self.native_status()
            director = observed.get('director') or {}
            rows = observed.get('workers')
            valid = (director.get('pid') == self.new_director['pid'] and
                director.get('process_starttime') == self.new_director['start_ticks'] and
                type(observed.get('observed_at')) in (int,float) and
                0 <= time.time()-observed['observed_at'] <= 15 and
                isinstance(rows,list) and len(rows) == 3 and len({row['pid'] for row in rows}) == 3)
            if valid:
                for row in rows:
                    actual = process_identity(row.get('pid'))
                    valid = valid and (actual is not None and actual['start_ticks'] == row.get('process_starttime')
                        and actual['ppid'] == self.new_director['pid'] and type(row.get('heartbeat_at')) in (int,float)
                        and 0 <= time.time()-row['heartbeat_at'] <= 20)
            if valid:
                proof = self.leaf_proof(state,rows)
                if proof:
                    snapshot = {'at':time.time(),'workers':rows}
                    if first is None:
                        first = snapshot
                    previous = {row['pid']:row for row in first['workers']}
                    same = set(previous) == {row['pid'] for row in rows}
                    advanced = same and all(row['process_starttime'] == previous[row['pid']]['process_starttime']
                        and row['heartbeat_at'] > previous[row['pid']]['heartbeat_at'] for row in rows)
                    if snapshot['at']-first['at'] >= 2 and advanced:
                        return {'new_leaf':proof,'process_snapshots':[first,snapshot],
                            'queue_preservation':{'original_ids':len(original),'missing_original_ids':[],
                                'historical_claim_receipt_entries':len(historical),'changed_historical_claim_receipt_ids':[],
                                'new_ids':sorted(set(state['tasks'])-set(original)),
                                'inert_track_startup_quarantine':sorted(self.inert_tracks),
                                'inert_track_claims_results_unchanged':True},
                            'native_loss_recovery_exercised':False,
                            'recovery_regression_scope':'INDEPENDENTLY_VERIFIED_LOCAL_PROCESSES_ONLY'}
            time.sleep(.5)
        raise Hold('HOLD_FOUR_QUEUE_RECOVERY_ACCEPTANCE_PENDING_NO_REPLAY')

    def snapshot(self):
        return {'schema':'NOX_CURRENT_FOUR_QUEUE_RECOVERY_INSTALL_V1','request':self.request,
            'source_sha':self.source,'status':self.phase,'accepted':self.accepted,
            'files_installed':self.installed,'before':{name:{'sha256':digest(raw),
                'identity':metadata(info)} for name,(raw,info) in self.before.items()},
            'old_director':self.old_director,'new_director':self.new_director,
            'restored_director':self.restored_director,'admission_release_intent':self.released,
            'source_replace_attempts':list(self.replace_attempts),'rollback_attempts':list(self.rollback_attempts),
            'prior_attempt_detected':self.prior_attempt,'reconcile_required':not self.accepted,
            'original_tasks_accepted':0,'model_calls_by_installer':0,'model_reloads':0,
            'counter_writes':0,'direct_queue_writes':0,'direct_s03_writes':0,
            'other_service_changes':0,'automatic_retry':False,
            'native_loss_recovery_exercised':False,
            'private_receipt_directory':str(ROOT/'state'/self.attempt_name) if self.attempt_fd else None}

    def run(self):
        evidence = None
        try:
            self.prepare()
            self.install_sources()
            evidence = self.acceptance()
            self.record('ACCEPTED',evidence)
            self.accepted = True
            self.phase = 'SOURCE_INSTALLED_THREE_WORKERS_NEW_HEALTH_LEAF_VERIFIED'
        except BaseException as exc:
            reason = str(exc) if isinstance(exc,Hold) else 'HOLD_FOUR_QUEUE_RECOVERY_NATIVE_OPERATION'
            self.phase = reason
            # Never rollback after unlock intent: the new task may already be
            # admitted, executing, done or have an UNKNOWN completion outcome.
            if self.stopped and not self.released:
                try:
                    self.rollback_before_release()
                except BaseException:
                    self.phase = reason+'_RECONCILE_REQUIRED'
            try:
                if self.attempt_fd is not None:
                    self.record('HOLD',{'reason':reason,'status':self.phase})
            except BaseException:
                pass
        result = self.snapshot()
        if evidence is not None:
            result['evidence'] = evidence
        return result

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()


def entry():
    installer = None
    try:
        installer = Installer(os.environ.get('NOX_OWNER_REQUEST_ID',''),os.environ.get('NOX_OWNER_SOURCE_SHA',''))
        return installer.run()
    finally:
        if installer is not None:
            installer.close()


def main():
    result = entry()
    print('NOX_MAINT_CURRENT_FOUR_QUEUE_RECOVERY='+json.dumps(result,ensure_ascii=False),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)


if __name__ == '__main__':
    main()
