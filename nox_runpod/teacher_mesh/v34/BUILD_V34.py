"""Source-only deterministic V34 packaging; only adds, never overwrites V33."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NAME='NOX_V34_NEURAL_S03_P02_FORGE_NATIVE_PATCH_AND_17_SOURCES_20261113.zip'
OUTPUT=ROOT.parent.parent / NAME

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    manifest={str(f.relative_to(ROOT)):sha(f) for f in sorted(ROOT.rglob('*'))
              if f.is_file() and '__pycache__' not in f.parts and f.name not in {'V34_SHA256_FILES.json'}}
    (ROOT/'V34_SHA256_FILES.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),'utf-8')
    with zipfile.ZipFile(OUTPUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(ROOT.rglob('*')):
            if not f.is_file() or '__pycache__' in f.parts or f.suffix == '.pyc':continue
            z.write(f,'NOX_V34/'+str(f.relative_to(ROOT)))
    with zipfile.ZipFile(OUTPUT) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('ZIP_CRC_FAILED:'+bad)
        if len(z.namelist()) < 275:raise RuntimeError('NO_LOSS_MEMBER_COUNT_HOLD')
    print(json.dumps({'path':str(OUTPUT),'bytes':OUTPUT.stat().st_size,'files':len(manifest)+1,
                     'sha256':sha(OUTPUT),'crc':'PASS'},indent=2))

if __name__=='__main__':main()
