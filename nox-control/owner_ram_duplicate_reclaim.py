#!/usr/bin/env python3
"""Replace one verified RAM duplicate with an atomic alias to its SSD original.

Only the two exact Hermes files from the pinned native inventory are admitted.
Both complete byte streams are hashed; the persistent file remains unchanged.
No process is stopped and no unique weight, training state or database is removed.
"""
import fcntl,hashlib,json,os,re,shutil,stat,tempfile,time,urllib.request
from pathlib import Path

ROOT=Path('/root/nox')
RAM=Path('/dev/shm/nox_t802u')
SSD_BASES=(ROOT/'offload_shm_t888u',ROOT/'models')
FOCUS=ROOT/'state/owner_storage/focus_6904156795.json'
FOCUS_SHA='1db66345cb3ebd1c87bfa39c89ce1dd532ab9b184c9602119e097b2cf45f6d86'
NAME='Hermes-3-Llama-3.1-8B.Q4_K_M.gguf'
SIZE=4920733824

def fail(code):raise RuntimeError(code)
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def plain(path):
 path=Path(path)
 for item in (*reversed(path.parents),path):
  if item.is_symlink():fail('HOLD_RAM_DUPLICATE_SYMLINK')
 return path
def identity(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
def full_hash(path):
 path=plain(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  before=os.fstat(stream.fileno())
  if not stat.S_ISREG(before.st_mode) or before.st_size!=SIZE or before.st_uid!=os.geteuid():fail('HOLD_RAM_DUPLICATE_FILE_IDENTITY')
  h=hashlib.sha256()
  for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
  if identity(os.fstat(stream.fileno()))!=identity(before) or identity(path.stat())!=identity(before):fail('HOLD_RAM_DUPLICATE_CHANGED_DURING_HASH')
 return h.hexdigest(),before
def healthy():
 with urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=5) as response:
  if response.status!=200:fail('HOLD_RAM_DUPLICATE_CHAT_HEALTH')
def atomic_json(path,value):
 path=plain(path);path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.duplicate-receipt-',dir=path.parent)
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'w') as output:json.dump(value,output);output.flush();os.fsync(output.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def choose(rows):
 selected=[row for row in rows if Path(row.get('path','')).name==NAME]
 ram=[row for row in selected if Path(row['path']).is_relative_to(RAM)]
 ssd=[row for row in selected if any(Path(row['path']).is_relative_to(base) for base in SSD_BASES)]
 if len(ram)!=1 or len(ssd)!=1:fail('HOLD_RAM_DUPLICATE_EXACT_PAIR')
 for row in (ram[0],ssd[0]):
  path=plain(row['path']);info=path.stat()
  if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)!=(row['device'],row['inode'],SIZE,row['mtime_ns']):fail('HOLD_RAM_DUPLICATE_INVENTORY_CHANGED')
 return Path(ram[0]['path']),Path(ssd[0]['path'])
def replace_duplicate(ram,ssd):
 ram_sha,ram_info=full_hash(ram);ssd_sha,ssd_info=full_hash(ssd)
 if ram_sha!=ssd_sha:fail('HOLD_RAM_DUPLICATE_BYTES_DIFFER')
 if ram_info.st_dev!=RAM.stat().st_dev or ram_info.st_dev==ssd_info.st_dev:fail('HOLD_RAM_DUPLICATE_TIER_IDENTITY')
 if any((ROOT/name).exists() or (ROOT/name).is_symlink() for name in ('STOP','STOP.flag','stop.flag','.stop','state/STOP')):fail('HOLD_OWNER_STOP')
 healthy()
 temporary=ram.with_name('.'+NAME+'.ssd-alias-'+str(os.getpid()))
 if temporary.exists() or temporary.is_symlink():fail('HOLD_RAM_DUPLICATE_ALIAS_COLLISION')
 try:
  os.symlink(str(ssd),temporary)
  if identity(ram.stat())!=identity(ram_info) or identity(ssd.stat())!=identity(ssd_info):fail('HOLD_RAM_DUPLICATE_CHANGED_BEFORE_SWAP')
  os.replace(temporary,ram)
 finally:
  if temporary.is_symlink():temporary.unlink()
 if not ram.is_symlink() or ram.resolve()!=ssd or identity(ram.stat())!=identity(ssd_info):fail('HOLD_RAM_DUPLICATE_ALIAS_READBACK')
 healthy()
 return {'name':NAME,'bytes':SIZE,'sha256':ssd_sha,'source_path':str(ssd),'warm_alias_path':str(ram),
         'persistent_source_unchanged':True,'alias_readback_verified':True,'unique_weights_deleted':0,
         'ram_duplicate_allocated_bytes_replaced':ram_info.st_blocks*512,
         'active_mappings_may_delay_physical_reclaim':True}
def main():
 request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
 if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_OWNER_CONTEXT')
 area=plain(ROOT/'state/owner_storage');area.mkdir(mode=0o700,exist_ok=True)
 lock=os.open(plain(ROOT/'state/owner_maintenance.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  descriptor=os.open(plain(FOCUS),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  with os.fdopen(descriptor,'rb') as stream:
   info=os.fstat(stream.fileno())
   if not stat.S_ISREG(info.st_mode) or info.st_size>262144:fail('HOLD_RAM_DUPLICATE_INVENTORY_TYPE_OR_SIZE')
   raw=stream.read(262145)
  if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=FOCUS_SHA:fail('HOLD_RAM_DUPLICATE_INVENTORY_PIN')
  inventory=json.loads(raw)
  if inventory.get('schema')!='NOX_OWNER_STORAGE_FOCUS_V1' or inventory.get('request')!='6904156795':fail('HOLD_RAM_DUPLICATE_INVENTORY_SCHEMA')
  ram,ssd=choose(inventory['large_files']);before=shutil.disk_usage(RAM).free
  result=replace_duplicate(ram,ssd)
  result.update(schema='NOX_OWNER_RAM_DUPLICATE_ALIAS_V1',request=request,source_sha=source,
                state='FULL_SHA_VERIFIED_RAM_DUPLICATE_REPLACED_WITH_SSD_ALIAS',
                shm_free_before=before,shm_free_after=shutil.disk_usage(RAM).free,finished=time.time(),
                concurrent_media_downloads_may_change_free_bytes=True)
  atomic_json(area/('ram_duplicate_'+request+'.json'),result);emit('ram_duplicate_alias_receipt',result)
  print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 finally:os.close(lock)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  reason=str(exc);emit('ram_duplicate_hold',{'reason':reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__});raise SystemExit(2)
