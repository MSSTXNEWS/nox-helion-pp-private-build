"""Build the exact reviewed runtime source staging entry; local only."""
from pathlib import Path
import ast
import base64
import gzip
import hashlib
import json

HERE=Path(__file__).resolve().parent
BASE=HERE.parent

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def collect_sources(base, lock):
    files={}
    for source,prefix in [('integrations_bridge/nox_integrations','runtime/nox_integrations'),('warm_weights_controller/nox_warm','runtime/nox_warm')]:
        root=base/source
        for path in sorted(root.glob('*.py')):
            if path.is_symlink() or not path.is_file():raise ValueError('INPUT_NOT_REGULAR')
            name=prefix+'/'+path.name;raw=path.read_bytes()
            if len(raw)>250000 or sha(raw)!=lock['file_pins'].get(name):raise ValueError('INPUT_PIN_DRIFT:'+name)
            text=raw.decode('utf-8');ast.parse(text,filename=name);files[name]=text
    if set(files)!=set(lock['file_pins']):raise ValueError('INPUT_FILE_SET_DRIFT')
    return files

def main():
    lock=json.loads((HERE/'inputs.lock.json').read_text())
    files=collect_sources(BASE,lock);pins={name:sha(text.encode()) for name,text in files.items()}
    bundle=canonical({'files':files,'sha256':pins})
    if len(bundle)>2*1024*1024:raise ValueError('BUNDLE_TOO_LARGE')
    packed=gzip.compress(bundle,mtime=0)
    if len(packed)>512*1024:raise ValueError('PACKED_BUNDLE_TOO_LARGE')
    bundle_sha=sha(bundle)
    template=(HERE/'entry.template.py').read_text()
    source=template.replace('BUNDLE_SHA256_VALUE',bundle_sha).replace('BUNDLE_JSON_BASE64_VALUE',base64.b64encode(packed).decode())
    ast.parse(source)
    if 'BUNDLE_SHA256_VALUE' in source or 'BUNDLE_JSON_BASE64_VALUE' in source:raise ValueError('UNFILLED_TEMPLATE')
    target=HERE/'owner_runtime_source_stage_20261117.py';target.write_text(source)
    manifest={'schema':'NOX_RUNTIME_SOURCE_STAGING_MANIFEST_V1','source_staging_only':True,'native_executed':False,'runtime_bound':False,'source_commits':lock['source_commits'],'reviewed_behavior_commits':lock['reviewed_behavior_commits'],'files':len(files),'source_bytes':sum(len(x.encode()) for x in files.values()),'bundle_bytes':len(bundle),'packed_bytes':len(packed),'bundle_sha256':bundle_sha,'destination':'/root/nox/extensions/drive_first_20261117_'+bundle_sha[:12],'entry':target.name,'entry_bytes':target.stat().st_size,'entry_sha256':sha(target.read_bytes()),'file_pins':[{'path':n,'bytes':len(files[n].encode()),'sha256':pins[n]} for n in sorted(files)],'input_lock_sha256':sha((HERE/'inputs.lock.json').read_bytes()),'template_sha256':sha((HERE/'entry.template.py').read_bytes()),'completion_marker_scope':'SOURCE_INSTALLED_NOT_BOUND only; never chat/native runtime acceptance'}
    (HERE/'STAGING_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ['files','source_bytes','bundle_bytes','bundle_sha256','entry_bytes','entry_sha256','destination']}))
if __name__=='__main__':main()
