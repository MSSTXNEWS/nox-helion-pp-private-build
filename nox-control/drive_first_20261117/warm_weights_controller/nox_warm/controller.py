"""No daemon, no private task queue: called by the existing OneHost dispatcher."""
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
from .cache import AtomicCache, file_sha256, warm_pages, Paused

MiB = 1024 * 1024
RAM_TRANSFER_ALLOWANCE = 64 * MiB


class Hold(RuntimeError):
    pass


def is_protected(group):
    names=(str(group.get('id',''))+' '+str(group.get('role',''))).lower().replace('-',' ').replace('_',' ').split()
    return group.get('protected') is True or bool(set(names)&{'core','chat','engram','backbone','primary'}) or 'engram' in group.get('cache_path','').lower()


@dataclass(frozen=True)
class Snapshot:
    current: int
    maximum: int | None
    host_available: int
    available: int
    shmem: int
    file: int
    anon: int
    psi_some_avg10: float
    psi_full_avg10: float
    inactive_file: int = 0
    active_file: int = 0
    file_mapped: int = 0
    reclaimable_candidate_upper_bound: int = 0
    reclaimable_guaranteed: int = 0


def read_snapshot(cgroup='/sys/fs/cgroup', meminfo='/proc/meminfo'):
    """memory.current already includes charged shmem; never add it as free RAM."""
    try:
        root = Path(cgroup)
        current = int((root/'memory.current').read_text().strip())
        raw_max = (root/'memory.max').read_text().strip()
        maximum = None if raw_max == 'max' else int(raw_max)
        stat = dict(line.split() for line in (root/'memory.stat').read_text().splitlines())
        host = {}
        for line in Path(meminfo).read_text().splitlines():
            k, _, rest = line.partition(':'); host[k] = rest.split()
        host_available = int(host['MemAvailable'][0]) * 1024
        pressure = {}
        for line in (root/'memory.pressure').read_text().splitlines():
            kind, *pairs = line.split(); pressure[kind] = dict(x.split('=',1) for x in pairs)
        some = float(pressure['some']['avg10']); full = float(pressure['full']['avg10'])
        if min(current, host_available) < 0 or maximum is not None and maximum < 0:
            raise ValueError('negative accounting')
        if not all(math.isfinite(x) and 0 <= x <= 100 for x in [some, full]):
            raise ValueError('invalid PSI')
        available = min(host_available, max(0, maximum-current)) if maximum is not None else host_available
        return Snapshot(current, maximum, host_available, available,
                        int(stat.get('shmem',0)), int(stat.get('file',0)), int(stat.get('anon',0)), some, full,
                        int(stat.get('inactive_file',0)),int(stat.get('active_file',0)),int(stat.get('file_mapped',0)),
                        int(stat.get('inactive_file',0)),0)
    except (OSError, ValueError, KeyError) as exc:
        raise Hold('MEMORY_ACCOUNTING_UNAVAILABLE') from exc


def load_manifest(path):
    data = json.loads(Path(path).read_text())
    if data.get('schema') != 'NOX_WARM_MANIFEST_V1':
        raise ValueError('MANIFEST_SCHEMA')
    if data.get('source_policy','DRIVE_FIRST')!='DRIVE_FIRST':raise ValueError('DRIVE_FIRST_REQUIRED')
    if data.get('startup_storage','ownedRAM') not in ['ownedRAM','warmSSD']:raise ValueError('INVALID_STARTUP_STORAGE')
    if data.get('startup_storage','ownedRAM')=='warmSSD' and data.get('allow_ssd_cache') is not True:raise ValueError('SSD_CACHE_REQUIRES_EXPLICIT_OPT_IN')
    groups = data.get('groups')
    if not isinstance(groups,list) or not groups or len(groups)>128:
        raise ValueError('MODEL_GROUPS_REQUIRED')
    seen=set()
    for g in groups:
        if not isinstance(g,dict) or not isinstance(g.get('id'),str) or not g['id'] or g['id'] in seen:
            raise ValueError('INVALID_GROUP_ID')
        seen.add(g['id'])
        for k in ['size_bytes','ram_load_bytes','gpu_load_bytes','priority','warm_bytes']:
            if type(g.get(k)) is not int or g[k] < 0:
                raise ValueError('INVALID_NONNEGATIVE_INTEGER:'+k)
        if g['size_bytes'] <= 0 or g['warm_bytes'] > g['size_bytes']:
            raise ValueError('INVALID_SIZE_OR_WARM_RANGE')
        if not isinstance(g.get('sha256'),str) or len(g['sha256'])!=64 or any(x not in '0123456789abcdef' for x in g['sha256']):
            raise ValueError('PINNED_SHA256_REQUIRED')
        for k in ['remote_path','cache_path']:
            value=g.get(k)
            if not isinstance(value,str) or not value or Path(value).is_absolute() or '..' in Path(value).parts or '://' in value:
                raise ValueError('RELATIVE_PATH_REQUIRED:'+k)
        if g.get('tier') not in ['coldDrive','warmSSD','RAM','GPU']:
            raise ValueError('INVALID_TIER')
        if not isinstance(g.get('modes'),list) or not set(g['modes']) <= {'WORK','TRAIN'}:
            raise ValueError('INVALID_MODES')
        for k in ['startup_preload','protected','may_unload']:
            if type(g.get(k)) is not bool: raise ValueError('BOOLEAN_REQUIRED:'+k)
        if is_protected(g) and g['may_unload']:raise ValueError('PROTECTED_UNLOAD_CONTRADICTION')
    budget=data.get('budgets',{})
    for k in ['chat_reserve_bytes','train_reserve_bytes','system_reserve_bytes','ssd_reserve_bytes','startup_transfer_bytes','startup_warm_bytes']:
        if type(budget.get(k)) is not int or budget[k] < 0:raise ValueError('INVALID_BUDGET:'+k)
    if 'startup_ram_bytes' in budget and (type(budget['startup_ram_bytes']) is not int or budget['startup_ram_bytes']<0):raise ValueError('INVALID_BUDGET:startup_ram_bytes')
    if type(budget.get('startup_max_groups',6)) is not int or not 1<=budget.get('startup_max_groups',6)<=24:raise ValueError('INVALID_STARTUP_GROUP_CAP')
    for mode in ['WORK','TRAIN']:
        ids=data.get('mode_groups',{}).get(mode)
        if not isinstance(ids,list) or len(ids)!=len(set(ids)) or not set(ids)<=seen:raise ValueError('INVALID_MODE_GROUPS')
        if any(mode not in g['modes'] for g in groups if g['id'] in ids):raise ValueError('GROUP_MODE_MISMATCH')
    return data


def atomic_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    if path.is_symlink() or tmp.is_symlink():raise Hold('SYMLINK_JOURNAL')
    with tmp.open('w') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


class CommandHooks:
    """Exact administrator-owned command allowlist. No shell or prompt interpolation.

    Every hook receives a small JSON request on stdin and must emit one JSON receipt.
    Commands, executable SHA256 and timeout are configuration, never model output.
    """
    NAMES={'drain','checkpoint','pause','resume','unload','load','health','inspect_operation','resource_admission','resource_release','owner_activity'}
    def __init__(self, config):
        self.commands=config

    def __call__(self, name, payload):
        if name not in self.NAMES or name not in self.commands:raise Hold('HOST_CALLBACK_UNBOUND:'+name)
        spec=self.commands[name];argv=spec.get('argv')
        if not isinstance(argv,list) or not argv or not all(isinstance(x,str) for x in argv):raise Hold('INVALID_HOOK_ARGV')
        executable=Path(argv[0])
        if not executable.is_absolute() or not executable.is_file() or executable.is_symlink():raise Hold('HOOK_EXECUTABLE_NOT_PINNED')
        if file_sha256(executable)!=spec.get('executable_sha256'):raise Hold('HOOK_EXECUTABLE_SHA_CHANGED')
        timeout=spec.get('timeout_seconds',30)
        if type(timeout) not in [int,float] or not 0<timeout<=120:raise Hold('INVALID_HOOK_TIMEOUT')
        result=subprocess.run(argv,input=json.dumps(payload),text=True,capture_output=True,
                              shell=False,timeout=timeout,check=False)
        if result.returncode!=0:raise Hold('HOST_CALLBACK_FAILED:'+name)
        if len(result.stdout)>65536:raise Hold('HOOK_RECEIPT_TOO_LARGE')
        try:receipt=json.loads(result.stdout)
        except ValueError as exc:raise Hold('HOOK_RECEIPT_NOT_JSON') from exc
        if not isinstance(receipt,dict):raise Hold('HOOK_RECEIPT_NOT_OBJECT')
        return receipt


class Controller:
    def __init__(self, manifest, cache_root, journal_path, *, snapshot=read_snapshot,
                 hooks=None, download_verified=None, host_resource_admission=None, host_release_resource=None, owner_should_pause=None,
                 download_memfd_verified=None, host_reserve_ram=None, host_release_ram=None, persistent_host=False, owned_ram_registry=None):
        self.manifest=manifest;self.groups={g['id']:g for g in manifest['groups']}
        self.cache=AtomicCache(cache_root);self.journal_path=Path(journal_path)
        self.snapshot=snapshot;self.hooks=hooks;self.download_verified=download_verified
        self.host_resource_admission=host_resource_admission
        self.host_release_resource=host_release_resource
        self.owner_should_pause=owner_should_pause
        self.download_memfd_verified=download_memfd_verified
        self.host_reserve_ram=host_reserve_ram;self.host_release_ram=host_release_ram
        self.persistent_host=persistent_host is True
        self._ram_handles=owned_ram_registry if owned_ram_registry is not None else {}
        self.data=json.loads(self.journal_path.read_text()) if self.journal_path.exists() else {
            'schema':'NOX_WARM_JOURNAL_V1','mode':'UNKNOWN','loaded':[],'operations':{},'events':[]}
        if self.data.get('schema')!='NOX_WARM_JOURNAL_V1':raise Hold('JOURNAL_SCHEMA')

    def reserve(self, mode):
        b=self.manifest['budgets']
        return b['system_reserve_bytes']+b['chat_reserve_bytes']+(b['train_reserve_bytes'] if mode=='TRAIN' else 0)

    def admit(self, bytes_needed, mode='WORK'):
        s=self.snapshot();limit=self.reserve(mode)
        if s.psi_full_avg10>5 or s.psi_some_avg10>20:raise Hold('MEMORY_PRESSURE')
        if bytes_needed+limit>s.available:raise Hold('INSUFFICIENT_CGROUP_HEADROOM')
        return asdict(s)

    def _persist(self):atomic_json(self.journal_path,self.data)

    def _op(self, key, name, payload):
        if self.hooks is None:raise Hold('HOST_CALLBACKS_UNBOUND')
        fingerprint=hashlib.sha256(json.dumps([name,payload],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        old=self.data['operations'].get(key)
        if old:
            if old['fingerprint']!=fingerprint:raise Hold('OPERATION_KEY_CONFLICT')
            if old['state']=='DONE':return old['receipt']
            check=self.hooks('inspect_operation',{'operation_key':key,'name':name})
            if check.get('state')=='DONE' and isinstance(check.get('receipt'),dict):
                receipt=check['receipt']
                if receipt.get('ok') is not True or receipt.get('operation_key')!=key:raise Hold('INVALID_RECONCILE_RECEIPT')
                old.update(state='DONE',receipt=receipt);self._persist();return receipt
            if check.get('state')!='NOT_STARTED':raise Hold('UNCERTAIN_OPERATION_REQUIRES_RECONCILE')
        self.data['operations'][key]={'name':name,'payload':payload,'fingerprint':fingerprint,'state':'STARTED'};self._persist()
        receipt=self.hooks(name,dict(payload,operation_key=key))
        if receipt.get('ok') is not True or receipt.get('operation_key')!=key:
            raise Hold('HOST_RECEIPT_NOT_ACCEPTED:'+name)
        self.data['operations'][key].update(state='DONE',receipt=receipt);self._persist();return receipt

    def adopt_verified_state(self, mode, loaded, receipt):
        """Host supplies an authoritative current snapshot; UNKNOWN is never WORK-ready."""
        if mode not in ['WORK','TRAIN','PAUSED_TRAIN'] or not set(loaded)<=set(self.groups):raise ValueError('INVALID_HOST_STATE')
        if receipt.get('verified') is not True or not receipt.get('source') or not receipt.get('observed_at'):raise Hold('HOST_STATE_UNVERIFIED')
        if mode=='PAUSED_TRAIN' and not self.data.get('training_checkpoint'):raise Hold('PAUSED_CHECKPOINT_UNVERIFIED')
        pending=self.data.get('transition')
        if pending and pending.get('status') in ['STARTED','HOLD']:
            if receipt.get('settled_transition_id')!=pending['id'] or receipt.get('pending_operations_settled') is not True:
                raise Hold('PENDING_EFFECTS_NOT_SETTLED')
            lease=pending.get('admission')
            if (receipt.get('resource_lease_settled') is not True
                or (lease and receipt.get('settled_lease_id')!=lease.get('lease_id'))
                or (lease and (type(receipt.get('settled_fencing_token')) is not int
                               or receipt.get('settled_fencing_token')!=lease.get('fencing_token')))
                or (not lease and receipt.get('settled_resource_request_id')!=pending['id'])):
                raise Hold('PENDING_RESOURCE_LEASE_NOT_SETTLED')
            for key,operation in self.data['operations'].items():
                if key.startswith(pending['id']+':') and operation.get('state')=='STARTED':
                    operation.update(state='RECONCILED',state_before_reconcile='STARTED',
                                     settled_by_transition_id=pending['id'])
            pending['reconciliation_receipt']=receipt
            pending['status']='RECONCILED'
        self.data.update(mode=mode,loaded=list(loaded),host_state_receipt=receipt);self._persist()

    def _cache_guard(self, should_pause=None):
        if (not callable(self.owner_should_pause)
            or (should_pause is not None and not callable(should_pause))
            or not callable(self.host_resource_admission) or not callable(self.host_release_resource)):
            raise Hold('CACHE_HOST_LEASE_OR_OWNER_ACTIVITY_UNBOUND')
        def guarded_pause():
            value=self.owner_should_pause()
            if type(value) is not bool:raise Hold('OWNER_ACTIVITY_UNVERIFIED')
            if value:return True
            extra=False if should_pause is None else should_pause()
            if type(extra) is not bool:raise Hold('LOCAL_PAUSE_STATE_UNVERIFIED')
            return extra
        if guarded_pause():raise Hold('OWNER_ACTIVE_OR_PAUSE_REQUESTED')
        return guarded_pause

    def _cache_lease(self, entry, needed, warm):
        previous=self.data.get('cache_lease_operation',{})
        if (self.data.get('cache_lease_reconcile') or
            previous and previous.get('state') not in ['RELEASED','RECONCILED','DENIED']):
            raise Hold('CACHE_LEASE_RECONCILE_REQUIRED')
        epoch=self.data.get('cache_lease_epoch',0)
        if type(epoch) is not int or epoch<0:raise Hold('CACHE_LEASE_EPOCH_UNVERIFIED')
        epoch+=1
        identity=hashlib.sha256(json.dumps([entry['id'],entry['sha256']],separators=(',',':')).encode()).hexdigest()
        request={'operation':'cache','transition_id':'cache:'+identity+':'+str(epoch),
            'group':entry['id'],'cache_path':entry['cache_path'],'ram_bytes':needed+warm,'gpu_bytes':0}
        pending={'state':'ADMISSION_PENDING','request':request,'lease':None}
        self.data.update(cache_lease_epoch=epoch,cache_lease_operation=pending);self._persist()
        try:receipt=self.host_resource_admission(dict(request))
        except BaseException:
            pending['state']='UNKNOWN';self._persist();raise
        if isinstance(receipt,dict) and receipt.get('granted') is False:
            pending['state']='DENIED';self._persist();raise Hold('HOST_RESOURCE_ADMISSION_DENIED')
        if (not isinstance(receipt,dict) or receipt.get('granted') is not True or receipt.get('scope')!='host'
            or not receipt.get('lease_id') or type(receipt.get('fencing_token')) is not int):
            pending['state']='UNKNOWN';self._persist();raise Hold('HOST_RESOURCE_ADMISSION_DENIED')
        pending.update(state='HELD',lease=receipt,release_retry_authorized=False);self._persist()
        return receipt

    def _cache_release(self, lease):
        pending=self.data.get('cache_lease_operation',{})
        if (pending.get('state')!='HELD' or pending.get('lease')!=lease):
            raise Hold('CACHE_LEASE_RECONCILE_REQUIRED')
        pending.update(state='RELEASE_PENDING',release_retry_authorized=False);self._persist()
        try:result=self.host_release_resource(dict(lease))
        except BaseException as exc:
            pending['state']='UNKNOWN';self.data['cache_lease_reconcile']=lease;self._persist()
            if not isinstance(exc,Exception):raise
            raise Hold('CACHE_RESOURCE_RELEASE_UNCONFIRMED') from None
        if not isinstance(result,dict) or result.get('released') is not True:
            pending['state']='UNKNOWN';self.data['cache_lease_reconcile']=lease;self._persist()
            raise Hold('CACHE_RESOURCE_RELEASE_UNCONFIRMED')
        pending['state']='RELEASED';self.data.pop('cache_lease_reconcile',None);self._persist()

    def reconcile_cache_lease(self, receipt):
        """Consume exact host readback; no host admission/release is called here."""
        pending=self.data.get('cache_lease_operation')
        if pending is None and self.data.get('cache_lease_reconcile'):
            pending={'state':'UNKNOWN','lease':self.data['cache_lease_reconcile'],'request':None}
        if not pending or pending.get('state') not in ['ADMISSION_PENDING','HELD','RELEASE_PENDING','UNKNOWN']:
            raise Hold('NO_PENDING_CACHE_LEASE')
        if (not isinstance(receipt,dict) or receipt.get('verified') is not True
            or not receipt.get('source') or not receipt.get('observed_at')
            or type(receipt.get('released')) is not bool):raise Hold('CACHE_LEASE_READBACK_UNVERIFIED')
        lease=pending.get('lease')
        if lease:
            if (receipt.get('lease_id')!=lease.get('lease_id') or type(receipt.get('fencing_token')) is not int
                or receipt.get('fencing_token')!=lease.get('fencing_token')):
                raise Hold('CACHE_LEASE_READBACK_UNVERIFIED')
        elif (receipt.get('settled_resource_request_id')!=(pending.get('request') or {}).get('transition_id')
              or not receipt.get('settled_resource_request_id')):
            raise Hold('CACHE_LEASE_READBACK_UNVERIFIED')
        if not lease and receipt['released'] is not True:raise Hold('CACHE_RESOURCE_REQUEST_NOT_SETTLED')
        self.data['cache_lease_operation']=pending
        pending.update(state='RECONCILED' if receipt['released'] else 'HELD',
                       release_retry_authorized=not receipt['released'],readback=receipt)
        if receipt['released']:self.data.pop('cache_lease_reconcile',None)
        self._persist()
        return {'status':'CACHE_LEASE_READBACK_VERIFIED','lease_released':receipt['released'],
                'native_release_performed':False}

    def release_reconciled_cache_lease(self):
        """One explicit retry only after host readback confirms this lease held."""
        pending=self.data.get('cache_lease_operation',{})
        if pending.get('state')!='HELD' or pending.get('release_retry_authorized') is not True:
            raise Hold('CACHE_RELEASE_RETRY_NOT_AUTHORIZED')
        self._cache_release(pending['lease'])
        return {'status':'CACHE_LEASE_RELEASED','lease_released':True}

    def cache_local(self, group_id, source, *, apply=False, should_pause=None):
        if self.manifest.get('allow_ssd_cache') is not True:raise Hold('SSD_CACHE_REQUIRES_EXPLICIT_OPT_IN')
        g=self.groups[group_id];self.admit(g['size_bytes'],'TRAIN')
        if not apply:return {'status':'DRY_RUN','group':group_id,'size_bytes':g['size_bytes']}
        pause=self._cache_guard(should_pause);lease=self._cache_lease(g,g['size_bytes'],0)
        try:
            def guard():
                if pause():return True
                self.admit(MiB,'TRAIN');return False
            return self.cache.stage_local(g,source,should_pause=guard)
        finally:self._cache_release(lease)

    def startup(self, *, apply=False, should_pause=None):
        if self.manifest.get('startup_storage','ownedRAM')=='ownedRAM':
            return self._startup_ram(apply=apply,should_pause=should_pause)
        if self.manifest.get('allow_ssd_cache') is not True:raise Hold('SSD_CACHE_REQUIRES_EXPLICIT_OPT_IN')
        b=self.manifest['budgets'];transfer=0;warming=0;rows=[]
        for g in sorted(self.groups.values(),key=lambda x:(-x['priority'],x['id'])):
            if not g['startup_preload'] or 'WORK' not in g['modes']:continue
            if len(rows)>=b.get('startup_max_groups',6):break
            needed=0 if self.cache.verify(g,allow_hash=False) else g['size_bytes']
            warm=min(g['warm_bytes'],max(0,b['startup_warm_bytes']-warming))
            row={'group':g['id'],'apply':apply,'status':'PLANNED','download_bytes':needed,'warm_bytes':warm}
            lease=None
            try:
                if transfer+needed>b['startup_transfer_bytes']:raise Hold('STARTUP_TRANSFER_CAP')
                # Download buffers and page cache charge memory; full object size is the conservative gate.
                self.admit(needed+warm,'TRAIN') # preserve both CHAT and future TRAIN reserve.
                if shutil.disk_usage(self.cache.root).free<needed+b['ssd_reserve_bytes']:raise Hold('SSD_HEADROOM')
                if apply:
                    pause=self._cache_guard(should_pause);lease=self._cache_lease(g,needed,warm)
                    if pause():raise Hold('COOPERATIVE_PAUSE')
                    if needed:
                        if self.download_verified is None:raise Hold('DRIVE_DOWNLOAD_CALLBACK_UNBOUND')
                        receipt=self.download_verified(g['remote_path'],g['cache_path'],g['sha256'],g['size_bytes'],should_pause=pause)
                        def hash_admission():
                            if pause():raise Hold('COOPERATIVE_PAUSE')
                            self.admit(MiB,'TRAIN')
                        if not isinstance(receipt,dict) or receipt.get('status') not in ['downloaded_verified','cache_hit_verified'] or not self.cache.verify(g,before_chunk=hash_admission):raise Hold('CACHE_READBACK_FAILED')
                    if warm:row['warming']=warm_pages(self.cache.path(g['cache_path']),warm,admission=lambda n:self.admit(n,'TRAIN'),should_pause=pause)
                    row['status']='CACHED_VERIFIED_RAM_HINT' if warm else 'CACHED_VERIFIED'
                    if row.get('warming',{}).get('status')=='WARM_PAUSED':row['status']='WARM_PAUSED'
                transfer+=needed;warming+=warm
            except (Hold,ValueError,Paused) as exc:row.update(status='HOLD',reason=str(exc))
            finally:
                if lease:
                    try:self._cache_release(lease)
                    except Exception:row.update(status='HOLD',reason='CACHE_RESOURCE_RELEASE_UNCONFIRMED')
            rows.append(row)
        return {'apply':apply,'selected':rows,'transfer_bytes':transfer,'warm_hint_bytes':warming,'all_drive_preloaded':False,'gpu_loaded':False}

    def _ram_valid(self, group_id):
        h=self._ram_handles.get(group_id);g=self.groups[group_id]
        if h is None:return False
        try:
            fd=h.fileno()
            seals=fcntl.fcntl(fd,getattr(fcntl,'F_GET_SEALS',1034))
            own_name=os.readlink('/proc/self/fd/'+str(fd)).startswith('/memfd:nox-drive-')
            return (own_name and seals&15==15 and h.sha256==g['sha256']
                    and h.size_bytes==g['size_bytes'] and os.fstat(fd).st_size==g['size_bytes'])
        except Exception:return False

    def ram_handle_for_loader(self, group_id):
        """Only trusted in-process host loader gets this handle; never expose its fd in receipts."""
        if not self.persistent_host or not self._ram_valid(group_id):raise Hold('OWNED_RAM_HANDLE_UNAVAILABLE')
        return self._ram_handles[group_id]

    def release_owned_ram(self, group_id, unload_receipt):
        if is_protected(self.groups[group_id]):raise Hold('PROTECTED_RUNTIME_GROUP')
        pending=self.data.get('transition',{})
        if (pending.get('status') in ['STARTED','HOLD']
            and group_id in set(pending.get('load',[])+pending.get('unload',[])+pending.get('loaded_before',[]))):
            raise Hold('RAM_TRANSITION_UNRECONCILED')
        if any(op.get('state')=='STARTED' and op.get('name') in ['load','unload']
               and op.get('payload',{}).get('group')==group_id for op in self.data['operations'].values()):
            raise Hold('RAM_LOADER_OPERATION_UNCERTAIN')
        if (group_id in self.data['loaded'] or unload_receipt.get('group')!=group_id
            or unload_receipt.get('loader_refs_released') is not True
            or unload_receipt.get('verified') is not True):raise Hold('RAM_LOADER_REFERENCES_UNCONFIRMED')
        h=self._ram_handles.get(group_id)
        if h is not None:
            identity=getattr(h,'release_identity',None)
            if not callable(identity):raise Hold('RAM_RELEASE_IDENTITY_UNBOUND')
            expected=identity()
            fields=('ram_handle_id','ram_lease_identity_sha256','ram_fencing_token')
            if (not isinstance(expected,dict) or not expected.get('ram_handle_id')
                or not expected.get('ram_lease_identity_sha256') or type(expected.get('ram_fencing_token')) is not int
                or type(unload_receipt.get('ram_fencing_token')) is not int
                or any(unload_receipt.get(k)!=expected.get(k) for k in fields)):
                raise Hold('RAM_RELEASE_PROOF_IDENTITY_MISMATCH')
            closed=h.close()
            if (not isinstance(closed,dict) or closed.get('closed') is not True
                or closed.get('lease_released') is not True):raise Hold('RAM_RELEASE_UNCONFIRMED')
        if self.data.get('ram_release_reconcile',{}).get(group_id):raise Hold('RAM_RELEASE_RECONCILE_REQUIRED')
        self._ram_handles.pop(group_id,None)
        return {'status':'OWNED_RAM_CLOSED' if h is not None else 'NO_OWNED_RAM_HANDLE',
                'group':group_id,'other_memfd_touched':False}

    def reconcile_owned_ram_release(self, group_id, receipt):
        """Record existing host's exact lease readback; never infer release from FD close."""
        h=self._ram_handles.get(group_id)
        pending=self.data.get('ram_release_reconcile',{}).get(group_id)
        if pending is None and h is None:raise Hold('NO_PENDING_RAM_RELEASE')
        if pending is not None:
            if (not isinstance(receipt,dict) or receipt.get('verified') is not True
                or receipt.get('lease_id')!=pending.get('lease_id')
                or type(receipt.get('fencing_token')) is not int
                or receipt.get('fencing_token')!=pending.get('fencing_token')
                or type(receipt.get('released')) is not bool):raise Hold('RAM_RELEASE_READBACK_UNVERIFIED')
        if h is not None:
            reconcile=getattr(h,'reconcile_release',None)
            if not callable(reconcile):raise Hold('RAM_RELEASE_RECONCILER_UNBOUND')
            result=reconcile(receipt)
            if not isinstance(result,dict) or result.get('closed') is not True:raise Hold('RAM_RELEASE_READBACK_UNVERIFIED')
        elif receipt['released'] is not True:
            raise Hold('RAM_LEASE_STILL_HELD')
        if receipt['released'] is True:
            self.data.setdefault('ram_release_reconcile',{}).pop(group_id,None);self._persist()
        return {'status':'RAM_RELEASE_READBACK_VERIFIED','group':group_id,
                'lease_released':receipt['released'],'native_query_performed':False}

    def _startup_ram(self,*,apply,should_pause):
        b=self.manifest['budgets'];total=0;transfer=0;rows=[]
        ram_cap=b.get('startup_ram_bytes',b['startup_warm_bytes'])
        for g in sorted(self.groups.values(),key=lambda x:(-x['priority'],x['id'])):
            if not g['startup_preload'] or 'WORK' not in g['modes']:continue
            if len(rows)>=b.get('startup_max_groups',6):break
            row={'group':g['id'],'status':'PLANNED','source':'verifiedDrive','tier':'ownedRAM','model_loaded':False};lease=None
            try:
                if self.data.get('ram_release_reconcile',{}).get(g['id']):raise Hold('RAM_RELEASE_RECONCILE_REQUIRED')
                if g['id'] in self.data['loaded']:
                    row['status']='JOURNAL_GROUP_NOT_DUPLICATED';row['live_readback_required']=True;rows.append(row);continue
                if is_protected(dict(g,protected=False)):
                    raise Hold('PRIMARY_CHAT_OR_ENGRAM_NO_DUPLICATE_PRELOAD')
                if self._ram_valid(g['id']):
                    row['status']='OWNED_RAM_ALREADY_VERIFIED';rows.append(row);continue
                if g['id'] in self._ram_handles:raise Hold('OWNED_RAM_HANDLE_REQUIRES_RECONCILE')
                required=g['size_bytes']+RAM_TRANSFER_ALLOWANCE
                if total+required>ram_cap or transfer+g['size_bytes']>b['startup_transfer_bytes']:raise Hold('STARTUP_RAM_OR_TRANSFER_CAP')
                self.admit(required,'TRAIN')
                if apply:
                    pause=self._cache_guard(should_pause)
                    if (not self.persistent_host or not callable(self.download_memfd_verified)
                        or not callable(self.host_reserve_ram) or not callable(self.host_release_ram)):
                        raise Hold('PERSISTENT_RAM_HOST_BINDING_REQUIRED')
                    lease=self._cache_lease(g,0,0) # writer claim only; retained RAM lease below owns the bytes.
                    def reserve(n):
                        if type(n) is not int or n!=required or total+n>ram_cap:raise Hold('RAM_RESERVATION_SIZE_OR_CAP')
                        if pause():raise Hold('COOPERATIVE_PAUSE')
                        self.admit(n,'TRAIN')
                        receipt=self.host_reserve_ram(n)
                        if (not isinstance(receipt,dict) or receipt.get('granted') is not True or receipt.get('scope')!='host'
                            or not receipt.get('lease_id') or type(receipt.get('fencing_token')) is not int):raise Hold('RAM_RESERVATION_DENIED')
                        return receipt
                    def release(receipt,group_id=g['id']):
                        try:result=self.host_release_ram(receipt)
                        except BaseException:
                            self.data.setdefault('ram_release_reconcile',{})[group_id]=receipt;self._persist()
                            raise
                        if not isinstance(result,dict) or result.get('released') is not True:
                            self.data.setdefault('ram_release_reconcile',{})[group_id]=receipt;self._persist()
                            raise Hold('RAM_RELEASE_UNCONFIRMED')
                        self.data.setdefault('ram_release_reconcile',{}).pop(group_id,None);self._persist()
                        return result
                    handle=self.download_memfd_verified(g['remote_path'],g['sha256'],g['size_bytes'],reserve_ram=reserve,release_ram=release,should_pause=pause)
                    self._ram_handles[g['id']]=handle
                    try:
                        if not self._ram_valid(g['id']):raise Hold('RAM_HANDLE_READBACK_FAILED')
                        digest=hashlib.sha256();offset=0
                        while offset<g['size_bytes']:
                            if pause():raise Hold('COOPERATIVE_PAUSE')
                            self.admit(MiB,'TRAIN')
                            block=os.pread(handle.fileno(),min(MiB,g['size_bytes']-offset),offset)
                            if not block:raise Hold('RAM_HANDLE_TRUNCATED')
                            digest.update(block);offset+=len(block)
                        if digest.hexdigest()!=g['sha256']:raise Hold('RAM_SHA_READBACK_FAILED')
                    except Exception:
                        closed=handle.close()
                        if (not isinstance(closed,dict) or closed.get('closed') is not True
                            or closed.get('lease_released') is not True):raise Hold('RAM_RELEASE_UNCONFIRMED')
                        self._ram_handles.pop(g['id'],None);raise
                    row['status']='OWNED_RAM_VERIFIED_NOT_MODEL'
                total+=required;transfer+=g['size_bytes']
                row.update(size_bytes=g['size_bytes'],sha256=g['sha256'],ram_reservation_bytes=required)
            except Exception as exc:row.update(status='HOLD',reason=str(exc)[:160])
            finally:
                if lease:
                    try:self._cache_release(lease)
                    except Exception:row.update(status='HOLD',reason='CACHE_RESOURCE_RELEASE_UNCONFIRMED')
            rows.append(row)
        return {'apply':apply,'source_policy':'DRIVE_FIRST','selected':rows,'ram_reservation_bytes':total,'transfer_bytes':transfer,
                'all_drive_preloaded':False,'gpu_loaded':False,'persistent_host_required':True}

    def transition(self,target,transition_id,*,apply=False):
        if target not in ['WORK','TRAIN','PAUSED_TRAIN']:raise ValueError('INVALID_TARGET')
        if not isinstance(transition_id,str) or not transition_id or len(transition_id)>128:raise ValueError('INVALID_TRANSITION_ID')
        mode=self.data['mode'];loaded=list(self.data['loaded'])
        previous=self.data.get('transition',{})
        if previous.get('id')==transition_id and previous.get('target')!=target:raise Hold('TRANSITION_KEY_CONFLICT')
        if previous.get('id')==transition_id and previous.get('status')=='RECONCILED':
            raise Hold('RECONCILED_TRANSITION_REQUIRES_NEW_ID')
        if previous.get('id')!=transition_id and any(k.startswith(transition_id+':') for k in self.data['operations']):
            raise Hold('STALE_TRANSITION_ID_REUSE')
        resuming=previous.get('id')==transition_id and previous.get('status') in ['STARTED','HOLD']
        if resuming:
            if previous.get('resource_lease_state') in ['ADMISSION_PENDING','RELEASE_PENDING','UNKNOWN']:
                raise Hold('HOST_RESOURCE_LEASE_RECONCILE_REQUIRED')
            mode=previous['source'];loaded=previous['loaded_before']
        if mode not in ['WORK','TRAIN','PAUSED_TRAIN']:raise Hold('CURRENT_HOST_STATE_UNVERIFIED')
        if self.data.get('transition',{}).get('id')==transition_id and self.data['transition'].get('status')=='DONE':
            if self.data['transition']['target']!=target:raise Hold('TRANSITION_KEY_CONFLICT')
            return self.data['transition']
        wanted=loaded if target=='PAUSED_TRAIN' else self.manifest['mode_groups'][target]
        if target!='PAUSED_TRAIN' and not wanted:raise Hold('TARGET_MODE_NOT_CONFIGURED')
        unload=[x for x in loaded if x not in wanted];load=[x for x in wanted if x not in loaded]
        if target=='PAUSED_TRAIN' and mode!='TRAIN':raise Hold('TRAIN_NOT_RUNNING')
        if any(is_protected(self.groups[x]) or not self.groups[x]['may_unload'] for x in unload):raise Hold('PROTECTED_RUNTIME_GROUP')
        bytes_needed=sum(self.groups[x]['ram_load_bytes'] for x in load)
        # No fictitious reclaim from pause or proposed unload. Fresh accounting must fit before action.
        if target=='PAUSED_TRAIN' or unload:
            self.snapshot() # drain/checkpoint/unload first; no reclaimed bytes assumed.
        else:
            self.admit(bytes_needed,'TRAIN' if target=='TRAIN' else 'WORK')
        ram_mode=self.manifest.get('startup_storage','ownedRAM')=='ownedRAM'
        if ram_mode:
            if not self.persistent_host or any(not self._ram_valid(x) for x in load):raise Hold('LOAD_OWNED_RAM_NOT_VERIFIED')
        elif any(not self.cache.verify(self.groups[x],allow_hash=False) for x in load):raise Hold('LOAD_CACHE_NOT_VERIFIED')
        plan={'id':transition_id,'source':mode,'target':target,'loaded_before':loaded,'unload':unload,'load':load,'status':'DRY_RUN','memory_reclaimed_by_pause':0}
        if not apply:return plan
        if self.hooks is None or self.host_resource_admission is None or self.host_release_resource is None:raise Hold('HOST_BINDING_REQUIRED')
        existing=self.data.get('transition')
        if existing and existing.get('status') in ['STARTED','HOLD'] and existing.get('id')!=transition_id:raise Hold('PENDING_TRANSITION_REQUIRES_RECONCILE')
        self.data['transition']=dict(plan,status='STARTED',admission=previous.get('admission') if resuming else None,
                                     resource_lease_state='ADMISSION_PENDING')
        self.data['mode']='TRANSITION';self._persist()
        try:
            admission=self.host_resource_admission({'transition_id':transition_id,'target':target,'expected_source_mode':mode,'expected_loaded':loaded,'load':load,'unload':unload,'ram_bytes':bytes_needed,'gpu_bytes':sum(self.groups[x]['gpu_load_bytes'] for x in load),'resume_lease':previous.get('admission') if resuming else None})
            if (not isinstance(admission,dict) or admission.get('granted') is not True or not admission.get('lease_id')
                or admission.get('scope')!='host' or type(admission.get('fencing_token')) is not int):raise Hold('HOST_RESOURCE_ADMISSION_DENIED')
            self.data['transition'].update(admission=admission,resource_lease_state='HELD');self._persist()
            if mode!=target:self._op(transition_id+':drain','drain',{'source':mode,'target':target})
            if mode=='TRAIN' and target!='TRAIN':
                cp=self._op(transition_id+':checkpoint','checkpoint',{'mode':'TRAIN'})
                ck=cp.get('checkpoint',{})
                required={'model','optimizer','scaler','rng','data_cursor'}
                if not required<=set(ck.get('components',[])) or not ck.get('durable_verified') or not ck.get('sha256') or not ck.get('path'):
                    raise Hold('CHECKPOINT_INCOMPLETE')
                if not Path(ck['path']).is_file() or file_sha256(ck['path'])!=ck['sha256']:raise Hold('CHECKPOINT_READBACK_FAILED')
                self.data['training_checkpoint']=ck;self._persist()
                self._op(transition_id+':pause','pause',{'mode':'TRAIN','checkpoint':ck})
                self.data['mode']='PAUSED_TRAIN';self._persist()
            for group in unload:
                self._op(transition_id+':unload:'+group,'unload',{'group':group,'preserve_source':True,'remove_memfd':False})
                if group in self.data['loaded']:self.data['loaded'].remove(group)
                self._persist()
            if target!='PAUSED_TRAIN':self.admit(bytes_needed,'TRAIN' if target=='TRAIN' else 'WORK')
            for group in load:
                source={'source_kind':'ownedRAM','owned_handle_key':group} if ram_mode else {'source_kind':'warmSSD','path':str(self.cache.path(self.groups[group]['cache_path']))}
                self._op(transition_id+':load:'+group,'load',{'group':group,**source,'sha256':self.groups[group]['sha256']})
                if group not in self.data['loaded']:self.data['loaded'].append(group)
                self._persist()
            if target=='TRAIN' and mode!='TRAIN':
                saved=self.data.get('training_checkpoint')
                if mode=='PAUSED_TRAIN' and not saved:raise Hold('PAUSED_CHECKPOINT_UNVERIFIED')
                if saved is not None:
                    required={'model','optimizer','scaler','rng','data_cursor'}
                    if (not isinstance(saved,dict) or not required<=set(saved.get('components',[]))
                        or saved.get('durable_verified') is not True or not saved.get('sha256') or not saved.get('path')):
                        raise Hold('CHECKPOINT_INCOMPLETE')
                    if not Path(saved['path']).is_file() or file_sha256(saved['path'])!=saved['sha256']:
                        raise Hold('CHECKPOINT_READBACK_FAILED')
                self._op(transition_id+':resume','resume',{'mode':'TRAIN','resume_from_verified_checkpoint':saved is not None,'checkpoint':saved})
            self._op(transition_id+':health','health',{'target':target,'loaded':self.data['loaded']})
            self.data['transition']['resource_lease_state']='RELEASE_PENDING';self._persist()
            released=self.host_release_resource(admission)
            if not isinstance(released,dict) or released.get('released') is not True:raise Hold('HOST_RESOURCE_RELEASE_UNCONFIRMED')
            self.data['mode']=target;self.data['transition'].update(status='DONE',verified_at=time.time(),resource_lease_released=True,resource_lease_state='RELEASED');self._persist()
            return self.data['transition']
        except Exception as exc:
            # Preserve durable successful steps; never claim automatic rollback or restored readiness.
            self.data['transition'].update(status='HOLD',error_code=type(exc).__name__,reason=str(exc)[:180],rollback_required=True)
            if self.data['transition'].get('resource_lease_state') in ['ADMISSION_PENDING','RELEASE_PENDING']:
                self.data['transition']['resource_lease_state']='UNKNOWN'
            self.data['mode']='HOLD'
            self._persist();raise

    def rollback_plan(self):
        """Explicit reconciliation-first rollback, never an invented successful restore.

        Host must settle pending operation keys, read current processes/resources,
        and call adopt_verified_state with that evidence before a reverse transition.
        No blind reload is issued while a timed-out GPU action may still be running.
        """
        t=self.data.get('transition')
        if not t or t.get('status') not in ['HOLD','STARTED']:raise Hold('NO_PENDING_TRANSITION')
        return {'status':'RECONCILE_REQUIRED','restore_mode':t['source'],'restore_groups':t['loaded_before'],
                'pending_operations':[k for k,v in self.data['operations'].items() if k.startswith(t['id']+':') and v['state']=='STARTED'],
                'admission_lease':t.get('admission'),'resource_request_id':t['id'],
                'resource_lease_state':t.get('resource_lease_state','UNKNOWN'),
                'memory_reclaimed_by_pause':0,'automatic_reload_performed':False}
