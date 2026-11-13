"""Verify all recorded sources in the unpacked V35 knowledge pack; no runtime changes."""
from pathlib import Path
import hashlib,json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
m=json.loads((root/'FILES_SHA256.json').read_text('utf-8'))
for relative, expected in m.items():
 p=root/relative
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
  raise SystemExit('FAIL_SHA_MISSING_OR_DRIFT:'+relative)
print(json.dumps({'state':'ALL_FILES_SHA_PASS','files':len(m),'s03_live_modified':False,'main_nox_weights_modified':False}))
