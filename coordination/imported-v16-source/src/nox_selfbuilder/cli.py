import argparse
import json
from pathlib import Path
from .seed import attest_seed

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=('verify-seed','model-candidates'))
    p.add_argument('--archive',default=str(Path(__file__).resolve().parents[2]/'assets'/'NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip'))
    args=p.parse_args()
    if args.command=='verify-seed':
        print(json.dumps(attest_seed(args.archive),ensure_ascii=False,indent=2))
    else:
        path=Path(__file__).resolve().parents[2]/'contracts'/'model_candidates.json'
        print(path.read_text('utf-8'))

if __name__=='__main__':main()
