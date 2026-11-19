"""Reproduce accepted WEB union from pinned V4 + V11 + source overlay.
Usage: python merge_web_source.py V4.zip V11.zip OVERLAY_ROOT OUTPUT_DIR
OVERLAY_ROOT is handoff/20261117/nox-v15-kit from the receipt commit.
"""
import hashlib,json,os,secrets,stat,sys
from pathlib import Path,PurePosixPath
from zipfile import ZipFile
V4='f3463ba1d8273bcccd3a5e701cb0a651dd4341e46750cbe88e0e287bf9a5a90a'
V11='1da2b3451ffbf4b47334a6f0f380aa6036179ac69af7b049a2b0e4b6914aab7d'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def _identity(info):
 return (info.st_dev,info.st_ino,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def _stable(stream,before):
 if _identity(os.fstat(stream.fileno()))!=_identity(before):raise ValueError('Source descriptor changed')

def _hash_opened(stream,before,output_fd=None):
 if not stat.S_ISREG(before.st_mode):raise ValueError('Source must be a regular file')
 digest=hashlib.sha256();remaining=before.st_size
 while True:
  block=stream.read(min(65536,remaining+1))
  if len(block)>remaining:raise ValueError('Source descriptor changed')
  if not block:
   if remaining:raise ValueError('Source descriptor changed')
   break
  remaining-=len(block);digest.update(block)
  if output_fd is not None:
   pending=memoryview(block)
   while pending:
    count=os.write(output_fd,pending)
    if count<=0:raise OSError('Short overlay write')
    pending=pending[count:]
 _stable(stream,before)
 return digest.hexdigest()

def _directory(path):
 absolute=Path(os.path.abspath(os.fspath(path)))
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
 try:
  for part in absolute.parts[1:]:
   child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
   os.close(fd);fd=child
  return fd
 except BaseException:
  os.close(fd);raise

def _target_info(directory,name):
 try:info=os.stat(name,dir_fd=directory,follow_symlinks=False)
 except FileNotFoundError:return None
 if not stat.S_ISREG(info.st_mode):raise ValueError('Unsafe overlay target')
 return info

def _copy_overlay(source,target,wanted,name):
 source_dir=_directory(source.parent)
 try:source_fd=os.open(source.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=source_dir)
 finally:os.close(source_dir)
 with os.fdopen(source_fd,'rb',buffering=0) as opened:
  before=os.fstat(opened.fileno())
  temporary='.nox-overlay-'+secrets.token_hex(16)+'.tmp';directory=_directory(target.parent)
  staged=None;published=False
  try:
   previous=_target_info(directory,target.name)
   # Let the kernel apply umask for a new destination; never synthesize execute bits.
   staged=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,
                  0o666 if previous is None else 0o600,dir_fd=directory)
   mode=stat.S_IMODE(os.fstat(staged).st_mode if previous is None else previous.st_mode)
   os.fchmod(staged,0o600)
   if _hash_opened(opened,before,staged)!=wanted:raise ValueError('Overlay hash mismatch: '+name)
   os.fchmod(staged,mode);os.fsync(staged)
   _stable(opened,before)
   current=_target_info(directory,target.name)
   if (None if current is None else _identity(current))!=(None if previous is None else _identity(previous)):
    raise ValueError('Overlay target changed')
   os.replace(temporary,target.name,src_dir_fd=directory,dst_dir_fd=directory)
   published=True;os.fsync(directory)
  finally:
   try:
    if staged is not None:
     try:
      if not published:
       try:current=os.stat(temporary,dir_fd=directory,follow_symlinks=False)
       except FileNotFoundError:current=None
       owned=os.fstat(staged)
       if current is not None and (current.st_dev,current.st_ino)==(owned.st_dev,owned.st_ino):
        os.unlink(temporary,dir_fd=directory)
     finally:os.close(staged)
   finally:os.close(directory)

MAX_ZIP_ENTRIES=4096
MAX_ZIP_TOTAL_UNCOMPRESSED=3*1024**3
MAX_ZIP_SINGLE_UNCOMPRESSED=512*1024**2
MAX_ZIP_RATIO=1000

def _zip_budget(infos,used_entries,used_bytes):
 if used_entries+len(infos)>MAX_ZIP_ENTRIES:raise ValueError('Zip entry budget exceeded')
 names=[i.filename for i in infos]
 if len(names)!=len(set(names)):raise ValueError('Duplicate zip member')
 for info in infos:
  name=info.filename;p=PurePosixPath(name)
  if (not name or p.is_absolute() or '..' in p.parts or '\\' in name or
      ':' in p.parts[0] or p.as_posix()!=name.rstrip('/')):
   raise ValueError('Unsafe source path')
  kind=stat.S_IFMT(info.external_attr>>16) if info.create_system==3 else 0
  if kind not in (0,stat.S_IFREG,stat.S_IFDIR):raise ValueError('Unsafe zip member kind')
  if (info.file_size<0 or info.compress_size<0 or
      info.file_size>MAX_ZIP_SINGLE_UNCOMPRESSED or
      used_bytes+info.file_size>MAX_ZIP_TOTAL_UNCOMPRESSED):
   raise ValueError('Zip uncompressed byte budget exceeded')
  if info.file_size>MAX_ZIP_RATIO*max(1,info.compress_size):
   raise ValueError('Zip expansion ratio exceeded')
  used_bytes+=info.file_size
 return used_entries+len(infos),used_bytes

def merge(v4,v11,overlay,out):
 if out.exists() and any(out.iterdir()):raise ValueError('Output must be empty')
 out.mkdir(parents=True,exist_ok=True)
 used_entries,used_bytes=0,0
 for archive,expected in [(v4,V4),(v11,V11)]:
  with archive.open('rb',buffering=0) as opened:
   before=os.fstat(opened.fileno())
   if _hash_opened(opened,before)!=expected:raise ValueError('Source hash mismatch: '+archive.name)
   opened.seek(0)
   with ZipFile(opened) as z:
    used_entries,used_bytes=_zip_budget(z.infolist(),used_entries,used_bytes)
    if z.testzip():raise ValueError('Source archive invalid')
    _stable(opened,before)
    z.extractall(out)
   _stable(opened,before)
 manifest=json.loads((overlay/'execution/pass49/role5/source-receipt.json').read_text())
 for name,wanted in manifest['source_overlay'].items():
  p=PurePosixPath(name) if isinstance(name,str) else None
  if (p is None or not name or p.is_absolute() or '..' in p.parts
      or '\\' in name or p.as_posix()!=name or not p.parts
      or ':' in p.parts[0]):raise ValueError('Unsafe overlay path')
  source=overlay/name
  # Overlay files must remain in the declared source tree; following a
  # source symlink would import an unrelated owner file into the result.
  for entry in (source,*source.parents):
   if entry==overlay.parent:break
   if entry.is_symlink():raise ValueError('Unsafe overlay source')
  target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
  _copy_overlay(source,target,wanted,name)
 return out
if __name__=='__main__':print(merge(*map(Path,sys.argv[1:])))
