"""Build a source-pinned native release entry; no network or native execution."""
from pathlib import Path
import ast, base64, gzip, hashlib, json

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
files={}
for root,prefix in ((BASE/'integrations_bridge/nox_integrations','runtime/nox_integrations'),(BASE/'warm_weights_controller/nox_warm','runtime/nox_warm')):
    for p in sorted(root.glob('*.py')):files[prefix+'/'+p.name]=p.read_text()
for src,dest in (
 ('warm_weights_controller/legacy_drive_first/install.py','legacy/install.py'),
 ('warm_weights_controller/legacy_drive_first/nox_teachers_warm.drive_first.sh','legacy/nox_teachers_warm.drive_first.sh'),
 ('native_resonance_patch/native_acceptance.py','acceptance/native_acceptance.py'),
 ('native_resonance_patch/native_integration_readset.py','acceptance/native_integration_readset.py'),
 ('model_evolution/gguf_metadata_probe.py','model/gguf_metadata_probe.py')):
    files[dest]=(BASE/src).read_text()
for name,text in files.items():
    if name.endswith('.py'):compile(text,name,'exec')
pins={name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
assert pins['acceptance/native_acceptance.py']=='633c2d1afce41f5d3d99d4fb1b6a5baf5aa488e9f3196426d0317bfa56cbf63b'
assert pins['acceptance/native_integration_readset.py']=='50ac0457ceae8dff31fe2c5a98befeb09dd9299cb67985e0f046e008037e4be7'
assert pins['model/gguf_metadata_probe.py']=='3a5567e83e0f06ed8c6881ef93350045fdcea3ecdde7d40ee562c98b9c1ad87d'
bundle=json.dumps({'files':files,'sha256':pins},sort_keys=True,separators=(',',':')).encode()
bundle_sha=hashlib.sha256(bundle).hexdigest()
template=(HERE/'entry.template.py').read_text()
source=template.replace('BUNDLE_JSON_BASE64',base64.b64encode(gzip.compress(bundle,mtime=0)).decode()).replace('BUNDLE_SHA256',bundle_sha)
compile(source,'owner_drive_first_release_20261117.py','exec')
(HERE/'owner_drive_first_release_20261117.py').write_text(source)
(HERE/'source_files.json').write_text(json.dumps({'files':files,'sha256':pins,'bundle_sha256':bundle_sha},ensure_ascii=False))
print(json.dumps({'files':len(files),'bundle_bytes':len(bundle),'entry_bytes':len(source.encode()),'bundle_sha256':bundle_sha,'entry_sha256':hashlib.sha256(source.encode()).hexdigest()}))
