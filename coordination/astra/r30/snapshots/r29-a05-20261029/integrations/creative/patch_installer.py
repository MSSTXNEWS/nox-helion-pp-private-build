"""Add only the compiled NOX creative child worker to original R13 NSIS payload before its SHA manifest.
This modifies a disposable CI checkout, never the historical R13 script or D02 images.
"""
from pathlib import Path
import sys
if len(sys.argv)!=3:raise SystemExit('USAGE patch_installer.py R13_BUILDER WORKER_DIR')
p=Path(sys.argv[1]);source=Path(sys.argv[2]).resolve()
if not source.is_dir() or not (source/'NOX_CreativeWorker.exe').is_file():raise SystemExit('CREATIVE_WORKER_EXE_NOT_BUILT')
s=p.read_text(encoding='utf-8-sig')
anchor='# Include the existing program files in the conservative NSIS manifest.'
if s.count(anchor)!=1:raise SystemExit('HOLD: R13 builder manifest anchor drift')
insert='''# Stage trusted sidecar worker as an on-demand child of the ONE visible WPF host.
$creativeWorkerDir='''+"'"+str(source).replace("'","''")+"'"+'''
$creativeTarget=Join-Path $payload 'Backend/Creative'
if (Test-Path -LiteralPath $creativeTarget) {throw 'CREATIVE_PAYLOAD_OVERWRITE_HOLD'}
Copy-Item -LiteralPath $creativeWorkerDir -Destination $creativeTarget -Recurse
if (!(Test-Path -LiteralPath (Join-Path $creativeTarget 'NOX_CreativeWorker.exe') -PathType Leaf)) {throw 'CREATIVE_PAYLOAD_MISSING_HOLD'}
'''
s=s.replace(anchor,insert+anchor)
p.write_text(s,encoding='utf-8')
print('CREATIVE_NSIS_PAYLOAD_PATCH_STAGED')
