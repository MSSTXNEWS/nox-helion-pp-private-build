"""Read-only completion of recovery6966231483; never repeat or undo its install."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

ROOT = Path('/root/nox')
REQUEST = '6966231483'
SOURCE = '9e495348bbe829daf80aa56dab5e4e8091133bb4'
ATTEMPT = 'state/four_queue_recovery_' + REQUEST
TASK = '1V14-01.native4q.recovery_health.20261118'
DIRECTOR = {'pid':3723052, 'start_ticks':175819458, 'ppid':114, 'pgrp':3723052}
PROTECTED = {'chat':(3266857,172046662), 'proxy':(3703386,175609570),
             'web':(3505392,173653097)}
DISPATCHER = '5f134b8b1915851de15318e23885951885ca84d6515ca1e48c56286862830db5'
INSTALLED = {
    'scripts/owner_subagent_dispatcher.py': {'dev':36,'ino':1152408711,'uid':0,'gid':0,'mode':420,'bytes':72630,'mtime_ns':1794965465146711958},
    'scripts/owner_subagent_instruction_truth.py': {'dev':36,'ino':1157000521,'uid':0,'gid':0,'mode':420,'bytes':2888,'mtime_ns':1794965465152711897},
    'config/owner_native_subagents.json': {'dev':36,'ino':50052644,'uid':0,'gid':0,'mode':384,'bytes':4790,'mtime_ns':1794965465157711847},
}
PINS = {
    'scripts/owner_subagent_dispatcher.py':DISPATCHER,
    'scripts/owner_subagent_instruction_truth.py':'95ba80a1175c545032a13ff0fd8942ebd39280dec3283f244d200527629ad048',
    'scripts/owner_autonomy_pool.py':'2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102',
    'scripts/owner_subagent_processes.py':'c1d5adfcc83300d749b42f66d50f41d5c62c4df52215e43cfc0b891e7c91101b',
    'scripts/owner_resource_policy.py':'3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834',
    'scripts/nox_dispatcher_t855u.py':'9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21',
    'scripts/chat_proxy.py':'1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62',
    'scripts/common.py':'618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
}


class Hold(Exception):
    pass


class Transient(Exception):
    pass


def require(value, reason):
    if not value:
        raise Hold('HOLD_RECOVERY_READBACK_' + reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,
                      separators=(',',':'),allow_nan=False).encode()


def metadata(info):
    return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
            'mode':stat.S_IMODE(info.st_mode),'bytes':info.st_size,'mtime_ns':info.st_mtime_ns}


def fingerprint(info):
    return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_mode','st_uid',
        'st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))


def process_identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    try:
        with Path('/proc',str(pid),'stat').open('rb') as stream:
            raw = stream.read(8193)
        require(0 < len(raw) <= 8192,'PROCESS_BOUND')
        fields = raw.rsplit(b') ',1)[1].split()
        if fields[0] not in (b'R',b'S',b'D',b'I'):
            return None
        return {'pid':pid,'start_ticks':int(fields[19]),'ppid':int(fields[1]),'pgrp':int(fields[2])}
    except (OSError,ValueError,IndexError):
        return None


class Reader:
    def __init__(self):
        self.deadline = time.monotonic()+30
        self.fds,self.edges,self.parents = [],[],{}
        self.lock = None
        self.transient_status_reads = 0
        self.last_health_status = None
        self.postimages = None

    def check(self):
        require(time.monotonic() < self.deadline,'DEADLINE_NO_REPLAY')

    def directory(self,path):
        key = str(path)
        if key in self.parents:
            return self.parents[key]
        flags = os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
        parent = os.open('/',flags); self.fds.append(parent)
        for part in Path(path).parts[1:]:
            self.check()
            child = os.open(part,flags,dir_fd=parent); self.fds.append(child)
            info = os.fstat(child)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0,'DIRECTORY_OWNER')
            identity = (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid)
            self.edges.append((parent,part,child,identity))
            parent = child
        self.parents[key] = parent
        return parent

    def read(self,relative,limit=262144, *, transient=False):
        self.check()
        require(not relative.startswith('/') and '..' not in Path(relative).parts,'READ_SCOPE')
        parent,name = relative.rsplit('/',1)
        directory = self.directory(ROOT/parent)
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                    and 0 < info.st_size <= limit,'READ_OWNER_BOUND')
            raw = os.pread(fd,limit+1,0)
            stable = (len(raw) == info.st_size and fingerprint(info) == fingerprint(os.fstat(fd))
                == fingerprint(os.stat(name,dir_fd=directory,follow_symlinks=False)))
            if not stable and transient:
                raise Transient('ATOMIC_SNAPSHOT_REPLACED')
            require(stable,'READ_DRIFT')
            return raw,info
        finally:
            os.close(fd)

    def acquire(self):
        require(os.geteuid() == 0,'OWNER_UID')
        parent = self.directory(ROOT/'state')
        self.lock = os.open('owner_maintenance.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        self.fds.append(self.lock)
        # SH permits the existing native health handler to run; EX would block it.
        fcntl.flock(self.lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        self.guard()

    def guard(self):
        self.check()
        for parent,name,child,identity in self.edges:
            opened,named = os.fstat(child),os.stat(name,dir_fd=parent,follow_symlinks=False)
            require(all((v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid) == identity
                        for v in (opened,named)),'DIRECTORY_DRIFT')
        opened = os.fstat(self.lock)
        named = os.stat('owner_maintenance.lock',dir_fd=self.directory(ROOT/'state'),follow_symlinks=False)
        require(stat.S_ISREG(opened.st_mode) and opened.st_uid == 0 and opened.st_nlink == 1
            and not opened.st_mode & 0o022 and (opened.st_dev,opened.st_ino) == (36,59886214)
            and (named.st_dev,named.st_ino,named.st_mode,named.st_uid) ==
                (opened.st_dev,opened.st_ino,opened.st_mode,opened.st_uid),'EXISTING_SHARED_LOCK')
        names = ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP',
                 'state/STOP.flag','state/OWNER_MAINTENANCE.flag')
        require(not any(path.exists() or path.is_symlink() for path in
            [*(ROOT/name for name in names),Path('/workspace/NOX_STOP')]),'OWNER_STOP')
        require(process_identity(DIRECTOR['pid']) == DIRECTOR,'DIRECTOR_LIFETIME')
        for label,(pid,start) in PROTECTED.items():
            row = process_identity(pid)
            require(row is not None and row['start_ticks'] == start,'PROTECTED_'+label.upper())

    def record(self,name):
        raw,info = self.read(ATTEMPT+'/'+name)
        require(stat.S_IMODE(info.st_mode) == 0o600,'PRIVATE_RECORD_MODE')
        value = json.loads(raw)
        require(isinstance(value,dict) and value.get('request') == REQUEST
            and value.get('source_sha') == SOURCE
            and value.get('schema') == 'NOX_CURRENT_FOUR_QUEUE_RECOVERY_INSTALL_V1','INSTALL_RECORD_CONTEXT')
        return value

    def prepare(self):
        self.acquire()
        attempt = os.fstat(self.directory(ROOT/ATTEMPT))
        require(stat.S_IMODE(attempt.st_mode) == 0o700,'PRIVATE_ATTEMPT_MODE')
        intent = self.record('01_INTENT.json')
        installed = self.record('09_SOURCE_INSTALLED.json')
        release = self.record('12_ADMISSION_RELEASE_INTENT.json')
        require(intent.get('phase') == 'INTENT' and installed.get('phase') == 'SOURCE_INSTALLED'
            and installed.get('files') == INSTALLED and release.get('phase') == 'ADMISSION_RELEASE_INTENT'
            and release.get('director') == DIRECTOR,'INSTALL_PHASE_BINDING')
        self.postimages = intent.get('composition',{}).get('source_postimages')
        require(isinstance(self.postimages,dict) and set(self.postimages) == set(INSTALLED)
            and release.get('native_source_postimages') ==
                {name:row.get('sha256') for name,row in self.postimages.items()},'INSTALL_POSTIMAGE_BINDING')
        self.source_guard()
        raw,info = self.read(ATTEMPT+'/queue_before.json',16*1024*1024)
        require(stat.S_IMODE(info.st_mode) == 0o600,'PRIVATE_QUEUE_MODE')
        before = json.loads(raw)
        require(isinstance(before,dict) and isinstance(before.get('tasks'),dict)
            and len(before['tasks']) <= 20000 and TASK not in before['tasks']
            and all(isinstance(row,dict) for row in before['tasks'].values()),'ORIGINAL_QUEUE_SCHEMA')
        return before

    def source_guard(self):
        for name,pin in PINS.items():
            require(digest(self.read(name)[0]) == pin,'SOURCE_SHA_'+name.rsplit('/',1)[-1])
        for name,identity in INSTALLED.items():
            raw,info = self.read(name)
            expected = self.postimages[name]
            require(metadata(info) == identity and digest(raw) == expected.get('sha256')
                and len(raw) == expected.get('bytes'),'INSTALLED_POSTIMAGE_IDENTITY')

    def native_status(self):
        value = json.loads(self.read('status/agents_t856u.json',2*1024*1024,transient=True)[0])
        result = value.get('native_subexecutors') if isinstance(value,dict) else None
        # Actual agents() first writes old_agents(), then adds native_subexecutors.
        if not isinstance(result,dict):
            raise Transient('NATIVE_FIELD_BETWEEN_TWO_STATUS_WRITES')
        return result

    def queue_proof(self,before):
        state = json.loads(self.read('state/dispatcher/state.json',16*1024*1024,transient=True)[0])
        require(isinstance(state,dict) and isinstance(state.get('tasks'),dict)
            and len(state['tasks']) <= 20000 and all(isinstance(v,dict) for v in state['tasks'].values()),'QUEUE_SCHEMA')
        prior,current = before['tasks'],state['tasks']
        require(set(prior) <= set(current),'QUEUE_IDS_LOST')
        historical = {key:row for key,row in prior.items() if row.get('status') in ('done','failed','blocked')}
        require(all(all(row.get(field) == current[key].get(field) for field in ('status','owner_claim','result'))
                    for key,row in historical.items()),'HISTORICAL_CLAIM_OR_RESULT_CHANGED')
        inert = []
        for key,row in prior.items():
            if row.get('status') != 'running':
                continue
            claim = row.get('owner_claim') or {}
            require(row.get('handler') == 'track' and isinstance(claim,dict)
                and re.fullmatch(r'[a-f0-9]{24}',str(claim.get('nonce',''))),'OLD_RUNNING_SCOPE')
            actual = current[key]
            require(all(row.get(field) == actual.get(field) for field in
                ('handler','params','owner_claim','result','retries')) and actual.get('status') == 'blocked'
                and actual.get('note') == 'HOLD: previous in-flight job requires child/process reconciliation before replay',
                'INERT_TRACK_QUARANTINE_CHANGED')
            inert.append(key)
        return state,{'original_ids':len(prior),'missing_original_ids':[],
            'historical_claim_receipt_entries':len(historical),'changed_historical_claim_receipt_ids':[],
            'new_ids':sorted(set(current)-set(prior)),'inert_track_startup_quarantine':sorted(inert),
            'inert_track_claims_results_unchanged':True}

    def leaf_proof(self,state,workers):
        task = state['tasks'].get(TASK)
        self.last_health_status = task.get('status') if isinstance(task,dict) else 'ABSENT'
        if not isinstance(task,dict) or task.get('status') != 'done':
            return None
        evidence = task.get('result') or {}
        receipt = evidence.get('receipt') or {}
        event = receipt.get('worker_result') or {}
        leaf = event.get('leaf_evidence') or {}
        worker = leaf.get('worker') or {}
        known = {(row['pid'],row['process_starttime']) for row in workers}
        require(receipt.get('task_id') == TASK and receipt.get('claim') == task.get('owner_claim')
            and receipt.get('source_sha256') == DISPATCHER
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
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0,'S03_FILE_OWNER')
            conn = sqlite3.connect((ROOT/'kb/knowledge.sqlite').as_uri()+'?mode=ro',uri=True,timeout=.2)
            try:
                conn.execute('PRAGMA query_only=ON')
                deadline = min(self.deadline,time.monotonic()+2)
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

    def run(self):
        before = self.prepare()
        first = None
        while time.monotonic() < self.deadline:
            self.guard()
            try:
                observed = self.native_status()
                state,preservation = self.queue_proof(before)
            except Transient:
                self.transient_status_reads += 1
                time.sleep(min(.25,max(0,self.deadline-time.monotonic())))
                continue
            owner,workers = observed.get('director') or {},observed.get('workers')
            valid = (owner.get('pid') == DIRECTOR['pid'] and owner.get('process_starttime') == DIRECTOR['start_ticks']
                and observed.get('mode') == 'NORMAL' and observed.get('target') == 3
                and type(observed.get('observed_at')) in (int,float)
                and 0 <= time.time()-observed['observed_at'] <= 15
                and isinstance(workers,list) and len(workers) == 3 and all(isinstance(v,dict) for v in workers)
                and len({v.get('pid') for v in workers}) == 3)
            if valid:
                for row in workers:
                    actual = process_identity(row.get('pid'))
                    valid = valid and (actual is not None and actual['start_ticks'] == row.get('process_starttime')
                        and actual['ppid'] == DIRECTOR['pid'] and type(row.get('heartbeat_at')) in (int,float)
                        and 0 <= time.time()-row['heartbeat_at'] <= 20)
            proof = self.leaf_proof(state,workers) if valid else None
            if proof:
                snapshot = {'at':time.time(),'workers':workers}
                if first is None:
                    first = snapshot
                previous = {row['pid']:row for row in first['workers']}
                same = set(previous) == {row['pid'] for row in workers}
                advanced = same and all(row['process_starttime'] == previous[row['pid']]['process_starttime']
                    and row['heartbeat_at'] > previous[row['pid']]['heartbeat_at'] for row in workers)
                if snapshot['at']-first['at'] >= 2 and advanced:
                    self.guard(); self.source_guard()
                    return {'accepted':True,'status':'THREE_WORKERS_NEW_HEALTH_AND_S03_VERIFIED',
                        'new_leaf':proof,'process_snapshots':[first,snapshot],
                        'queue_preservation':preservation,'postimages':self.postimages,'installed_identities':INSTALLED}
            time.sleep(min(.5,max(0,self.deadline-time.monotonic())))
        raise Hold('HOLD_RECOVERY_READBACK_ACCEPTANCE_PENDING_NO_REPLAY')

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)


def main():
    reader = Reader()
    result = {'accepted':False}
    try:
        result.update(reader.run())
    except BaseException as exc:
        result['status'] = str(exc) if isinstance(exc,Hold) else 'HOLD_RECOVERY_READBACK_UNKNOWN'
    finally:
        reader.close()
    result.update(schema='NOX_CURRENT_FOUR_QUEUE_RECOVERY_READBACK_V1',install_request=REQUEST,
        install_source_sha=SOURCE,new_director=DIRECTOR,transient_status_reads=reader.transient_status_reads,
        health_status=reader.last_health_status,reconcile_required=not result['accepted'],
        read_only=True,lock_mode='SH_EXISTING',application_file_writes=0,
        sqlite_auxiliary_io='POSSIBLE_WITH_MODE_RO_QUERY_ONLY',service_changes=0,process_signals=0,
        model_calls=0,counter_writes=0,queue_writes=0,s03_writes=0,health_resubmissions=0,
        native_loss_recovery_exercised=False,automatic_retry=False,original_tasks_accepted=0)
    print('NOX_MAINT_CURRENT_FOUR_QUEUE_RECOVERY_READBACK='+json.dumps(result,ensure_ascii=False),flush=True)
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)


if __name__ == '__main__':
    main()
