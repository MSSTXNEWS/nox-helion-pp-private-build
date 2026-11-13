#!/usr/bin/env python3
"""Add-only NOX WEB V29 patch from the verified physical V28 source archive.
Existing V27 main HOME, Resonance JS, original 14-world PBR and PC sources are
byte-for-byte pinned. Refuses unknown input. No Windows, S03 or live processes.
"""
from pathlib import Path
import os,sys,zipfile,hashlib,json,tempfile,time,datetime
BASE=Path(os.environ.get('NOX_MERGE_DIR','/mnt/data')).resolve()
ROOT=Path(__file__).resolve().parent
PREVIOUS=Path(os.environ.get('NOX_V28_INPUT_ZIP',BASE/'NOX_HELION_WEB_V28_V27_PC_GENESIS_UNIFIED_SOURCE_20261113.zip'))
OUTPUT=Path(os.environ.get('NOX_V29_OUTPUT_ZIP',BASE/'NOX_HELION_WEB_V29_V27_PC_GENESIS_UNIFIED_20261113.zip'))
EXPECTED='def872e6c81d407a57c96f1385438ee010c8cf7df89e0c74e5d61de2f9589905'
IMMUTABLE={
 'index.html':'f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17',
 'nox-home.mjs':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',
 'nox-engines/physical-worlds-v7.mjs':'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905',
 'assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp':'3253d26819a70b49259fdb2a56c2eaa2455c6878cb2ccb8d62b225ec6ccdfa22',
 'nox-chat.js':'d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce',
 'nox-function-catalog.js':'c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661',
}
def digest(data):return hashlib.sha256(data).hexdigest()
assert PREVIOUS.exists() and digest(PREVIOUS.read_bytes())==EXPECTED,'V28_SOURCE_DRIFT_HOLD'
with zipfile.ZipFile(PREVIOUS) as z:
 assert z.testzip() is None,'V28_BAD_CRC_HOLD'
 old={n.removeprefix('site/'):z.read(n) for n in z.namelist() if n.startswith('site/') and not n.endswith('/')}
 assert len(old)==1080,('V28_MEMBER_COUNT',len(old))
manifest=json.loads(old['SOURCE_MANIFEST_V28.json'])
assert len(manifest)==1077
for name,info in manifest.items():
 assert digest(old[name])==info['sha256'] and len(old[name])==info['bytes'],('V28_MANIFEST_MISMATCH',name)
mutations=['chat.html','memory.html','training.html','system.html']
new=dict(old)
for name in mutations:
 assert name in new,('MISSING_PATCH',name)
 if name=='system.html':
  target=b'href="/nox/dashboard"'; replacement=b'href="system.html#dashboard-overview"'
 else:
  target=b'nox-v28-pc-genesis-addons';replacement=b'nox-v29-pc-genesis-addons'
 assert new[name].count(target)==(1 if name=='system.html' else 2),('V28_PATCH_ANCHOR_DRIFT',name)
 new[name]=new[name].replace(target,replacement)
 assert new[name]!=old[name],('MISSING_DELTA',name)
for name in ['nox-v29-pc-genesis-addons.mjs','nox-v29-pc-genesis-addons.css']:
 assert name not in new
 new[name]=(ROOT/name).read_bytes()
# One original Resonance, plus a truthful compatibility route for PC hub/world.
assert 'resonance.html' not in new, 'NOX_PRIMARY_RESONANCE_ROUTE_COLLISION_HOLD'
new['resonance.html']=(
 '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
 '<meta name="viewport" content="width=device-width,initial-scale=1">'
 '<meta http-equiv="refresh" content="0;url=chat.html">'
 '<title>NOX HELION · Резонанс</title>'
 '<script>location.replace("./chat.html");</script>'
 '</head><body><a href="chat.html">Открыть основной Резонанс</a></body></html>\n'
).encode('utf-8')
for name in IMMUTABLE:
 assert digest(new[name])==IMMUTABLE[name] and new[name]==old[name],('NO_LOSS_FAIL',name)
for name in old:
 if name not in mutations:assert new[name]==old[name],('UNEXPECTED_CHANGE',name)
assert b'href="/nox/dashboard"' not in new['system.html']
assert b'href="system.html#dashboard-overview"' in new['system.html']
for name in ['chat.html','memory.html','training.html']:
 assert new[name].count(b'nox-v29-pc-genesis-addons.mjs')==1
assert new['index.html']==old['index.html']
for fname in ['test_v29_source.py','test_v29_chromium_component.py',
              'test_v29_pc_api_contract.cjs','test_v29_static_routes.py']:
 new['qa/v29/'+fname]=(ROOT/fname).read_bytes()
receipt={
 'schema':'NOX_HELION_WEB_V29_ONEPASS_SIX_TASKS_SOURCE_RECEIPT_V1',
 'date_utc':'2026-11-13T00:00:00Z',
 'scope':'WEB-only V27 PRIMARY plus PC V25/GENESIS addons; no new backend or active alternate chat',
 'source':{'v28_sha256':EXPECTED,'v27_source_head':'64053cead613ab646f7dcf05ea68479bab8bf434','pc_source_pr':251},
 'mutations':{name:{'before':digest(old[name]),'after':digest(new[name])} for name in mutations},
 'added':['nox-v29-pc-genesis-addons.mjs','nox-v29-pc-genesis-addons.css',
          'resonance.html','qa/v29/test_v29_source.py',
          'qa/v29/test_v29_chromium_component.py','qa/v29/test_v29_pc_api_contract.cjs',
          'qa/v29/test_v29_static_routes.py'],
 'immutable':IMMUTABLE,
 'web_tasks':{'monitoring_route':'FIXED_REAL_PAGE','pc_tools_primary_resonance':'INTEGRATED_READ_ONLY_SAME_ONEHOST','pc_memory_primary_page':'INTEGRATED_READ_ONLY_SAME_S03','genesis':'GATED_EXISTING_NATIVE_STATUS_AND_PROGRESS','browser_e2e':'SEPARATE_EVIDENCE_REQUIRED','wow30':'SOURCE_MATRIX_CHECKED_PHYSICAL_GPU_HOLD','preview':'DEPLOY_NOT_YET_CONFIRMED'},
 'native_onehost_live':'NOT_TESTED','physical_windows_gpu':'NOT_TESTED',
 'independent_merged_chromium':'NOT_TESTED',
 'production_modified':False,'release_accepted':False,
}
# Exclude receipts/manifests from self-referential manifest; every effective site source file is pinned.
exclude={'SOURCE_MANIFEST_V28.json','NOX_V28_UNIFIED_RECEIPT.json','SOURCE_MANIFEST_V29.json','NOX_V29_UNIFIED_RECEIPT.json'}
manifest29={name:{'sha256':digest(value),'bytes':len(value)} for name,value in sorted(new.items()) if name not in exclude}
new['SOURCE_MANIFEST_V29.json']=(json.dumps(manifest29,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
receipt['manifest_file_count']=len(manifest29)
receipt['manifest_sha256']=digest(new['SOURCE_MANIFEST_V29.json'])
receipt['final_member_count']=len(new)+1
new['NOX_V29_UNIFIED_RECEIPT.json']=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode()
# Exact source patches only. Extras kept for rollback but not imported into current active pages.
start=time.time()
fd,tmp=tempfile.mkstemp(prefix='nox-v29-',suffix='.zip',dir=OUTPUT.parent)
os.close(fd)
try:
 with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
  for name,body in sorted(new.items()):
   info=zipfile.ZipInfo('site/'+name,(2026,11,13,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
   info.external_attr=0o644 << 16
   z.writestr(info,body,compress_type=zipfile.ZIP_DEFLATED,compresslevel=4)
 with zipfile.ZipFile(tmp) as z:
  assert z.testzip() is None,'OUTPUT_ZIP_CRC_FAIL'
  assert len(z.namelist())==len(new),'OUTPUT_MEMBER_COUNT'
  for name in old:
   if name not in mutations:assert z.read('site/'+name)==old[name],('OLD_FILE_CHANGED',name)
  assert digest(z.read('site/index.html'))==IMMUTABLE['index.html']
  assert all(digest(z.read('site/'+n))==info['sha256'] for n,info in manifest29.items())
 os.replace(tmp,OUTPUT)
except BaseException:
 os.unlink(tmp)
 raise
sha=digest(OUTPUT.read_bytes());result={'path':str(OUTPUT),'bytes':OUTPUT.stat().st_size,'sha256':sha,'members':len(new),'manifest':len(manifest29),'CRC':'PASS','elapsed_seconds':round(time.time()-start,1),'native':'HOLD','production_modified':False}
(BASE/'NOX_WEB_V29_PHYSICAL_BUILD_RECEIPT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
