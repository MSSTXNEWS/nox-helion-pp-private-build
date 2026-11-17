"""Local key preparation and restore; never prints private data or file names."""
import argparse, hashlib, json
from pathlib import Path
import owner_cp55_cipher as core
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--private-dir',required=True);prep.add_argument('--scope-file',required=True)
    ver=sub.add_parser('restore');ver.add_argument('--private-dir',required=True);ver.add_argument('--parts-dir',required=True)
    ver.add_argument('--destination',required=True);ver.add_argument('--source',required=True);ver.add_argument('--request',required=True)
    a=p.parse_args()
    if a.command=='prepare':r=core.prepare(a.private_dir,hashlib.sha256(Path(a.scope_file).read_bytes()).hexdigest())
    else:
        full=core.restore(a.parts_dir,a.private_dir,a.destination,a.source,a.request)
        r={k:v for k,v in full.items() if k!='files'};r['file_count']=len(full['files'])
    print(json.dumps(r,sort_keys=True))
if __name__=='__main__':
    try:main()
    except Exception as e:
        import re
        s=str(e);s=s if re.fullmatch('HOLD_[A-Z0-9_]+',s) else 'HOLD_CP55_LOCAL_'+type(e).__name__.upper()
        print(json.dumps({'state':s,'cleanup_authorized':False}));raise SystemExit(2)
