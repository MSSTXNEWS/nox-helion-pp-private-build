"""NOX V53: read-only provenance for existing S03, OneHost and original WEB.

Runs under verified Vast V51 temporary-SSH session. It checks only metadata
and does not read actual memory records, credentials or chat message contents.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,sqlite3,hashlib,re,json,socket,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V53_S03_ONEHOST_PROVENANCE_V1')
canon=Path('/root/nox')
known={
  'web_chat':'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/chat.html',
  'web_resonance':'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/resonance.html',
  'web_pc_chat':'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/chat.html',
  'web_js':'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-chat.js',
  'web_pc_js':'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/nox-chat.js',
  'dispatcher':'program/duty/dispatcher.py',
}
for label,rel in known.items():
    p=canon/rel
    present=p.is_file() and not p.is_symlink()
    print('NATIVE_CANON_'+label.upper()+'_EXISTS='+str(present).lower())
    if present:
        try:
            size=p.stat().st_size
            print('NATIVE_CANON_'+label.upper()+'_BYTES='+str(size))
            if size<=2000000 and (p.suffix in ('.py','.html','.js')):
                print('NATIVE_CANON_'+label.upper()+'_SHA256='+hashlib.sha256(p.read_bytes()).hexdigest())
        except OSError:pass
# File metadata ONLY: no memory records ever selected.
dbs=[
 Path('/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),
 Path('/root/nox/memory/infinite/nox_infinite_memory.sqlite3'),
 Path('/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3'),
]
for i,p in enumerate(dbs,1):
    label='NATIVE_S03_CANDIDATE_'+str(i)
    if not p.is_file():
        print(label+'_STATE=MISSING')
        continue
    print(label+'_SIZE_BYTES='+str(p.stat().st_size))
    try:
        con=sqlite3.connect('file:'+str(p)+'?mode=ro&immutable=1',uri=True,timeout=0.4)
        con.execute('PRAGMA query_only=ON')
        tables=[r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 40")]
        con.close()
        safe=[x for x in tables if re.fullmatch('[A-Za-z0-9_]{1,70}',x)]
        print(label+'_SCHEMA_READ=PASS_IMMUTABLE')
        print(label+'_TABLE_NAMES='+','.join(safe[:25]))
    except (sqlite3.DatabaseError,OSError):
        print(label+'_SCHEMA_READ=HOLD_UNAVAILABLE')
# Existing program source grep — counts and path-only proof, no source text.
patterns={'run_admin':b'run_admin','onehost':b'onehost',
          's03_append':b's03_append','queue_enqueue':b'queue_enqueue',
          'model_stream':b'model_stream'}
hits={k:[] for k in patterns}
scanned=0
for parent in [canon/'program',canon/'scripts',canon/'memory',canon/'sources']:
    if not parent.is_dir():continue
    for root,dirs,files in os.walk(parent,followlinks=False):
        depth=len(Path(root).relative_to(parent).parts)
        dirs[:]=[x for x in dirs if depth<4 and x not in
                 ('.git','.cache','venv','.venv','node_modules','__pycache__')][:30]
        for name in files[:200]:
            p=Path(root)/name
            if p.suffix.lower() not in ('.py','.js','.ts','.json','.sh','.ps1'):
                continue
            try:
                if p.stat().st_size>180000:continue
                blob=p.read_bytes().lower()
            except OSError:continue
            scanned+=1
            for k,needle in patterns.items():
                if needle in blob and len(hits[k])<8:
                    hits[k].append(str(p))
            if scanned>2200:break
        if scanned>2200:break
    if scanned>2200:break
print('NATIVE_ONEHOST_SOURCE_FILES_SCANNED='+str(scanned))
for k,files in hits.items():
    print('NATIVE_SOURCE_PATTERN_'+k.upper()+'_MATCH_COUNT='+str(len(files)))
    for p in files[:4]:
        print('NATIVE_SOURCE_PATTERN_'+k.upper()+'_PATH='+p[:175])
# Local TCP listeners only; no network access or authenticated requests.
try:
    process=subprocess.run(['ss','-H','-ltnp'],capture_output=True,
                           text=True,timeout=7)
    rows=[]
    if process.returncode==0:
        for line in process.stdout.splitlines()[:140]:
            fields=line.split()
            if len(fields)<5:continue
            local=fields[3]
            port=local.rsplit(':',1)[-1]
            if port.isdigit() and len(port)<=5:
                rows.append(int(port))
    print('NATIVE_LISTENING_TCP_PORTS='+json.dumps(sorted(set(rows))[:40]))
except (OSError,subprocess.TimeoutExpired):print('NATIVE_LISTENING_TCP_PORTS=HOLD')
# Process classification metadata, no args or env values printed.
counts={'memory':0,'server':0,'onehost':0,'training':0,'learn':0,
        'gpu':0,'embedding':0,'chat':0,'bridge':0}
for entry in os.listdir('/proc'):
    if not entry.isdigit():continue
    try:cmd=(Path('/proc')/entry/'cmdline').read_bytes()[:2000].replace(b'\0',b' ').lower()
    except OSError:continue
    for label in counts:
        if label.encode() in cmd:counts[label]+=1
print('NATIVE_PROCESS_CLASS_COUNTS='+json.dumps(counts,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as exc:
        print("NOX_V53_AUDIT="+str(exc) if str(exc).startswith("HOLD_") else "NOX_V53_AUDIT=HOLD")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print('NOX_V53_SSH_CLEANUP=HOLD')
            ok=False
    raise SystemExit(0 if ok else 2)
