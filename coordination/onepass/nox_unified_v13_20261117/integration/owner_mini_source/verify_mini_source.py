"""Read-only admission against the SINGLE current source manifest; never deploys."""
import argparse,json
from pathlib import Path
from stage_current_source import verify as verify_current,safe_source,sha

def verify(bundle,live_root=None,expected_sha=None):
    receipt,manifest,_=verify_current(Path(bundle).resolve().parents[1],expected_sha)
    if live_root:
        for source,target in manifest['runtime_targets'].items():
            current=safe_source(Path(live_root).resolve(),target)
            if sha(current.read_bytes())!=manifest['files'][source]:
                raise SystemExit('HOLD_LIVE_SOURCE_DIFFERS '+target)
        receipt['live_source_files_match']=True
    return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--live-root',type=Path);p.add_argument('--expected-sha256');a=p.parse_args();print(json.dumps(verify(a.bundle,a.live_root,a.expected_sha256)))
