#!/usr/bin/env python3
"""Restore a missing System.IO import in the disposable R08 code-only build.
Never modify the original hash-pinned archive or author-owned files in GitHub.
"""
from pathlib import Path
import hashlib,sys
assert len(sys.argv)==2
p=Path(sys.argv[1]).resolve()/'Packages/P05/InstallerRunReport.cs'
original=p.read_bytes(); expected='1a6fcfff72924260a9e913f8af26a7c1009482bbdef67b85e5c11c0709ca8a4e'
if hashlib.sha256(original).hexdigest()!=expected:raise SystemExit('HOLD_P05_STAGE3_PREIMAGE')
s=original.decode('utf-8'); needle='using System.Globalization;\n';assert s.startswith(needle) and 'using System.IO;' not in s
updated='using System.IO;\n'+s;p.write_bytes(updated.encode('utf-8'))
print('NOX_R08_P05_STAGE3_PINNED_IMPORT pre='+expected+' post='+hashlib.sha256(updated.encode()).hexdigest())