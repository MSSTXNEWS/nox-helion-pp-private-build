"""Reproduce accepted WEB union from pinned V4 + V11 + source overlay.
Usage: python merge_web_source.py V4.zip V11.zip OVERLAY_ROOT OUTPUT_DIR
OVERLAY_ROOT is handoff/20261117/nox-v15-kit from the receipt commit.
"""
import hashlib,json,shutil,sys
from pathlib import Path,PurePosixPath
from zipfile import ZipFile
V4='f3463ba1d8273bcccd3a5e701cb0a651dd4341e46750cbe88e0e287bf9a5a90a'
V11='1da2b3451ffbf4b47334a6f0f380aa6036179ac69af7b049a2b0e4b6914aab7d'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def merge(v4,v11,overlay,out):
 if out.exists() and any(out.iterdir()):raise ValueError('Output must be empty')
 out.mkdir(parents=True,exist_ok=True)
 for archive,expected in [(v4,V4),(v11,V11)]:
  if sha(archive)!=expected:raise ValueError('Source hash mismatch: '+archive.name)
  with ZipFile(archive) as z:
   if len(z.namelist())!=len(set(z.namelist())) or z.testzip():raise ValueError('Source archive invalid')
   for name in z.namelist():
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name:raise ValueError('Unsafe source path')
   z.extractall(out)
 manifest=json.loads((overlay/'execution/pass49/role5/source-receipt.json').read_text())
 for name,wanted in manifest['source_overlay'].items():
  source=overlay/name
  if sha(source)!=wanted:raise ValueError('Overlay hash mismatch: '+name)
  target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
 return out
if __name__=='__main__':print(merge(*map(Path,sys.argv[1:])))
