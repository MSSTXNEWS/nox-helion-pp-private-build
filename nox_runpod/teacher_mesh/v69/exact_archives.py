"""NOX V69: full SHA of four specific cold-source archives; no write."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time
_orig=c.api
def _api(method,path,key,data=None):
    r=_orig(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(25)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,stat,hashlib,json,re
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V69_EXACT_COLD_ARCHIVE_SHA_V1')
candidates={
 'backup':(Path('/root/nox/backup'),{165692771,164610213}),
 'incoming':(Path('/root/nox/incoming_t800u'),{85218466,85218272})
}
for root_label,(root,sizes) in candidates.items():
 results=[]
 for base,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()][:120]
  for name in files:
   p=Path(base)/name
   try:
    st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size not in sizes:continue
    if root_label=='backup' and p.suffix!='.gz':continue
    if root_label=='incoming' and p.suffix!='.zip':continue
    h=hashlib.sha256()
    with p.open('rb') as stream:
     for chunk in iter(lambda:stream.read(2*1024*1024),b''):h.update(chunk)
    after=p.stat()
    if after.st_size!=st.st_size or after.st_mtime_ns!=st.st_mtime_ns:raise RuntimeError('HOLD_ARCHIVE_CHANGED')
    rel=str(p.relative_to(root))
    # do not display credential filenames or private directory tree names
    basename=p.name if re.fullmatch(r'[A-Za-z0-9._-]{1,90}',p.name) and not re.search(r'(secret|token|pass|key|auth)',p.name,re.I) else 'REDACTED'
    results.append({'root':root_label,'bytes':st.st_size,
      'sha256':h.hexdigest(),'path_hint':hashlib.sha256(rel.encode()).hexdigest()[:24],
      'basename':basename,'mtime_ns':st.st_mtime_ns,'nlink':st.st_nlink})
  if len(results)>6:break
 for item in results[:6]:print('NATIVE_COLD_FILE='+json.dumps(item,separators=(',',':')))
 print('NATIVE_COLD_FILE_COUNT_'+root_label.upper()+'='+str(len(results)))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 c.REMOTE=REMOTE;c.api=_api
 ok=False
 try:ok=c.probe()
 except Exception as e:
  s=str(e)
  print('NOX_V69_SHA='+s if s.startswith('HOLD_') and len(s)<100 else 'NOX_V69_SHA=HOLD_NATIVE')
 finally:
  try:
   if not c.cleanup():ok=False
  except Exception:print('NOX_V69_SHA=HOLD_KEY_REVOKE');ok=False
 return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
