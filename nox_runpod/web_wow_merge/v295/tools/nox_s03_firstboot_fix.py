#!/usr/bin/env python3
"""SHA-locked patch for the *existing* NOX V25 server first-boot S03 bug.

No new backend. By default writes a new source file; never edits the original.
Preserves existing SQLite databases; cold empty S03 requires explicit env opt-in.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, sys

ORIGINAL_SHA256 = '4d5766cdd98333c9bfdfd394029debc07224d08b59ac54bdc60565130cd6143a'
BEFORE = '''        best = max(cands, key=_creator_count)
        shutil.copy2(best, DB_PATH)
        print("[NOX] память перенесена из", best)
'''
AFTER = '''        # Reuse a real existing S03 database. Never silently create a second memory.
        existing = [p for p in cands if os.path.isfile(p) and _creator_count(p) >= 0]
        if existing:
            best = max(existing, key=_creator_count)
            shutil.copy2(best, DB_PATH)
            print("[NOX] существующая память перенесена из", best)
        elif os.environ.get("NOX_ALLOW_EMPTY_S03_BOOTSTRAP") == "1":
            # Explicit, clean FIRST INSTALL only. Existing databases are never modified.
            new_db = sqlite3.connect(DB_PATH)
            try:
                new_db.execute("PRAGMA user_version=0")
                new_db.commit()
            finally:
                new_db.close()
            print("[NOX] создана новая пустая S03 по явному разрешению; не restored backup")
        else:
            raise RuntimeError(
                "NOX_S03_EXISTING_DATABASE_MISSING_HOLD: no verified S03 seed or "
                "existing SQLite; set NOX_DB to the original file. "
                "Fresh empty memory requires NOX_ALLOW_EMPTY_S03_BOOTSTRAP=1")
'''

def sha(b: bytes) -> str: return hashlib.sha256(b).hexdigest()

def patch_source(source: bytes) -> bytes:
    if sha(source) != ORIGINAL_SHA256:
        raise ValueError('NOX_ORIGINAL_SERVER_SOURCE_SHA_DRIFT_REFUSE_EDIT '+sha(source))
    text = source.decode('utf-8')
    if text.count(BEFORE) != 1:
        raise ValueError('NOX_BOOTSTRAP_ANCHOR_AMBIGUOUS')
    new = text.replace(BEFORE, AFTER)
    assert len(new) > len(text)
    return new.encode('utf-8')

def main():
    p=argparse.ArgumentParser(description='NOX S03 firstboot fail-closed patch (offline output only)')
    p.add_argument('--source', type=pathlib.Path, required=True)
    p.add_argument('--output', type=pathlib.Path, required=True)
    args=p.parse_args()
    if not args.source.is_file():raise ValueError('NOX_SOURCE_NOT_FOUND')
    if args.output.exists():raise ValueError('NOX_OUTPUT_EXISTS_NO_OVERWRITE')
    patched=patch_source(args.source.read_bytes())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as fp:fp.write(patched)
    result={'input':str(args.source),'input_sha256':ORIGINAL_SHA256,'output':str(args.output),
            'output_sha256':sha(patched),'runtime_updated':False,
            'original_memory_read_or_modified':False,'explicit_empty_s03_required':True}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('NOX_S03_PATCH_HOLD:',type(exc).__name__,str(exc),file=sys.stderr)
        raise SystemExit(2)
