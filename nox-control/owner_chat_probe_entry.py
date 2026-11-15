#!/usr/bin/env python3
"""Run the reviewed chat probe in the existing proxy interpreter."""
import base64,hashlib,json,subprocess
BUNDLE=__NOX_BUNDLE_JSON__
source=base64.b64decode(BUNDLE['owner_chat_probe.py'],validate=True)
compile(source,'<owner-chat-probe>','exec')
r=subprocess.run(['/root/nox/venv/bin/python','-'],input=source,capture_output=True,timeout=170)
for line in r.stdout.decode(errors='replace').splitlines():
    if line.startswith('NOX_MAINT_') and len(line)<180000:print(line,flush=True)
if r.returncode:
    print('NOX_MAINT_CHAT_PROBE_RETURN='+str(r.returncode),flush=True)
raise SystemExit(r.returncode)
