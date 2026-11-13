#!/usr/bin/env python3
"""Reproducible NOX HELION WEB V27 source-only consolidator.

Canonical: existing WEB V25.1 + real Windows PC V25 + 7 V24 Whisper assets
+ 10 original ONEPASS QA scripts + trusted-endpoint-only Genesis panel.
No production, model, S03, trained-weight, backend, or network changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone

BASE = Path('/mnt/data')
WEB = 'NOX_HELION_WEB_V25_1_CANDIDATE_20261112.zip'
PC25 = 'NOX_CHAT_V25_SOURCES_PC_20261112.zip'
PC24 = 'NOX_CHAT_V24_SOURCES_20261112.zip'
ONEPASS = 'NOX_HELION_ONEPASS_V2_HARDENED_20261112.zip'
PC_ROOT = 'NOX_CHAT_V24/web/'
OUTPUT = 'NOX_HELION_WEB_WOW_V27_UNIFIED_SOURCE_20261113.zip'
PC_EXPECTED = 743
V24_EXTRA_EXPECTED = 7
WEB_EXPECTED = 292
ONEPASS_EXPECTED = 302
PAGES = ('training.html', 'pc/resonance.html', 'pc/memory.html', 'pc/chat.html')
ROOT_QA = {'NOX_ONEPASS.mjs','NOX_LIVE_ONEHOST_E2E.mjs','START_NOX_ONEPASS.cmd','NOX_AGENT_FULL_FINISH.md','README_RU.md','README_V2_ADDITIONS.md','NOX_V2_STATE.md','test-onepass.mjs','SOURCE_MANIFEST.json','BUNDLE_RECEIPT_V2.json'}
MAX_COUNT = 5000
MAX_BYTES = 2 * 1024**3
PATTERNS = {'github_pat':rb'github_pat_[A-Za-z0-9_]{24,}', 'ghp':rb'ghp_[A-Za-z0-9]{28,}',
  'sk':rb'sk-[A-Za-z0-9]{28,}', 'google':rb'AIza[0-9A-Za-z_-]{30,}'}
PATS = {k:re.compile(x) for k,x in PATTERNS.items()}
STATIC_ABS = re.compile(rb"(?P<q>[\"'])(?:/)(?P<dir>vendor|v22|v23|v24|v25|predator|assets13|assets|nox-engines|nox-worlds|pages)/",re.I)
STATIC_INTERNAL = re.compile(rb"(?P<q>[\"'])/(?P<page>menu|world|hub)\.html",re.I)
HEX64 = re.compile('[0-9a-f]{64}')


def sha(b: bytes) -> str:return hashlib.sha256(b).hexdigest()

def sha_file(path:Path)->str:
  h=hashlib.sha256()
  with path.open('rb') as fp:
    for chunk in iter(lambda:fp.read(1048576),b''):h.update(chunk)
  return h.hexdigest()


def assert_safe_member(name):
  if (not name or name.startswith('/') or '\\' in name or ':' in name or '\x00' in name
      or any(p in ('','.', '..') or p.endswith((' ','.')) for p in name.split('/'))):
    raise ValueError('UNSAFE_ARCHIVE_MEMBER '+repr(name))
  if name != PurePosixPath(name).as_posix():raise ValueError('NON_CANONICAL_PATH '+repr(name))


def read_zip(path: Path):
  data={};folded=set();total=0
  with zipfile.ZipFile(path) as z:
    for f in z.infolist():
      if f.is_dir():continue
      assert_safe_member(f.filename)
      if (f.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP_SYMLINK_DENIED '+f.filename)
      if f.filename.casefold() in folded:raise ValueError('WINDOWS_CASE_COLLISION '+f.filename)
      folded.add(f.filename.casefold())
      if f.flag_bits&1:raise ValueError('ENCRYPTED_ZIP_DENIED '+f.filename)
      total+=f.file_size
      if total>MAX_BYTES or len(data)>=MAX_COUNT:raise ValueError('INPUT_ZIP_LIMIT')
      data[f.filename]=z.read(f)
  return data


def local_entry(title,target):
  # Trusted local route only, never an external page or second host.
  assert target in ('pc/resonance.html','pc/memory.html')
  t='Резонанс' if title=='chat' else 'Память S03'
  return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
     f'<meta name="viewport" content="width=device-width,initial-scale=1">'
     f'<meta http-equiv="refresh" content="0;url={target}">'
     f'<title>NOX HELION · {t}</title>'
     f'<script>location.replace({json.dumps(target,ensure_ascii=False)});</script>'
     f'</head><body><a href="{target}">{t} · открыть</a></body></html>\n').encode('utf-8')


def clean_v25_static(name,data):
  changed=[]
  # Exact known third-party vendor asset with public Firebase room-sharing key;
  # no external room persistence in private local NOX.
  if name == 'pages/_vendor/excalidraw/excalidraw.production.min.js':
    out,n=PATS['google'].subn(b'',data)
    if n: data=out;changed.append('VENDOR_EXCALIDRAW_PUBLIC_FIREBASE_KEY_REMOVED')
  if name.lower().endswith(('.html','.htm','.mjs','.js','.css','.json')):
    for label,rx in PATS.items():
      if rx.search(data):raise ValueError('POTENTIAL_SECRET_IN_STATIC_SOURCE '+label+' '+name)
    if name.lower().endswith(('.html','.htm','.mjs','.js','.css')):
      new=STATIC_ABS.sub(lambda m: m.group('q')+b'/pc/'+m.group('dir')+b'/',data)
      new=STATIC_INTERNAL.sub(lambda m:m.group('q')+b'/pc/'+m.group('page')+b'.html',new)
      if new != data:changed.append('ABSOLUTE_STATIC_URL_RESCOPED_TO_PC')
      data=new
  return data,changed


def inject_genesis_page(name,body):
  ref='../nox_genesis_live_panel.mjs' if name.startswith('pc/') else './nox_genesis_live_panel.mjs'
  tag=('<script type="module" src="'+ref+'"></script>\n').encode('ascii')
  if tag in body:raise ValueError('GENESIS_ALREADY_INJECTED')
  matches=list(re.finditer(rb'</body\s*>',body,re.I))
  if len(matches)!=1:raise ValueError('GENESIS_HTML_BODY_HOLD '+name)
  return body[:matches[0].start()]+tag+body[matches[0].start():]


def zip_write(z,name,data):
  assert_safe_member(name)
  info=zipfile.ZipInfo(name,date_time=(2026,11,13,0,0,0))
  info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
  z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)


def build(root:Path,out:Path,genesis:Path):
  paths={n:root/n for n in (WEB,PC25,PC24,ONEPASS)}
  for p in paths.values():
    if not p.is_file():raise ValueError('REQUIRED_SOURCE_MISSING '+str(p))
  if out.exists():raise ValueError('OUTPUT_EXISTS_REFUSE_OVERWRITE')
  source={n:read_zip(f) for n,f in paths.items()}
  web=source[WEB];a=source[PC25];b=source[PC24];op=source[ONEPASS]
  if len(web)!=WEB_EXPECTED:raise ValueError('WEB_COUNT_MISMATCH')
  qa={n:v for n,v in op.items() if not n.startswith('site/')}
  if len(op)!=ONEPASS_EXPECTED or set(qa)!=ROOT_QA:raise ValueError('ONEPASS_QA_ORIGINAL_COUNT_MISMATCH')
  if len([n for n in op if n.startswith('site/')])!=WEB_EXPECTED:raise ValueError('ONEPASS_WEB_COUNT_MISMATCH')
  for n,payload in web.items():
    if sha(op['site/'+n])!=sha(payload):raise ValueError('ONEPASS_WEB_SHA_MISMATCH '+n)
  for r in ('index.html','chat.html','memory.html','training.html','cinema.html','models.html','projects.html','system.html','settings.html','install.html'):
    if r not in web:raise ValueError('WEB_REQUIRED_PAGE_MISSING '+r)
  pc25={n[len(PC_ROOT):]:v for n,v in a.items() if n.startswith(PC_ROOT)}
  pc24={n[len(PC_ROOT):]:v for n,v in b.items() if n.startswith(PC_ROOT)}
  if len(pc25)!=PC_EXPECTED:raise ValueError('PC_V25_COUNT_MISMATCH '+str(len(pc25)))
  if any(not pc25.get(x) for x in ('chat.html','resonance.html','memory.html','index.html')):
    raise ValueError('V25_ORIGINAL_CHAT_OR_MEMORY_MISSING')
  extra=sorted(set(pc24)-set(pc25))
  if len(extra)!=V24_EXTRA_EXPECTED:raise ValueError('V24_EXTRA_COUNT_MISMATCH '+str(extra))
  if any(pc24[n]!=pc25[n] for n in set(pc24)&set(pc25)):
    raise ValueError('V24_V25_SHARED_CONTENT_DRIFT_HOLD')
  if not all(n.startswith('pages/_vendor/whisper-tiny/') for n in extra):raise ValueError('V24_EXTRA_NOT_WHISPER')
  print('INPUT_VERIFY',json.dumps({'web':len(web),'onepass':len(op),'pc25':len(pc25),'v24_whisper':extra},ensure_ascii=False))
  # Core canonical: WEB itself unchanged, except its chat+memory navigation entrypoints.
  site=dict(web)
  site['original_web_v25_1/chat.html']=web['chat.html']
  site['original_web_v25_1/memory.html']=web['memory.html']
  site['chat.html']=local_entry('chat','pc/resonance.html')
  site['memory.html']=local_entry('memory','pc/memory.html')
  site['resonance.html']=local_entry('chat','pc/resonance.html')
  rewrites={}; sanitized={}
  for n,payload in {**pc25,**{n:pc24[n] for n in extra}}.items():
    new,why=clean_v25_static(n,payload)
    if 'pc/'+n in site:raise ValueError('PC_PATH_COLLISION '+n)
    site['pc/'+n]=new
    if why:rewrites[n]=why
    if 'VENDOR_EXCALIDRAW_PUBLIC_FIREBASE_KEY_REMOVED' in why:sanitized[n]=True
  js=genesis.read_bytes()
  if sha(js)!='7fa46af4ffe60390ebbbfb13e1accb83bb24f510b36e327abcb69b39c4548c66':
    raise ValueError('GENESIS_ORIGINAL_JS_SHA_MISMATCH')
  old_pages={}
  for n in PAGES:
    if n not in site:raise ValueError('GENESIS_TARGET_MISSING '+n)
    old_pages[n]=sha(site[n])
    site[n]=inject_genesis_page(n,site[n])
  site['nox_genesis_live_panel.mjs']=js
  if site['index.html'] != web['index.html']:raise ValueError('NO_LOSS_D02_CHANGED')
  if len(site)!=1046:raise ValueError('SITE_MEMBER_COUNT_MISMATCH '+str(len(site)))
  for n in web:
    if n not in ('chat.html','memory.html','training.html') and site[n]!=web[n]:
      raise ValueError('WEB_NOLOSS_CHANGED '+n)
  original_unchanged=sum(site[n]==v for n,v in web.items() if n not in ('chat.html','memory.html','training.html'))
  # All 10 original ONEPASS QA files are preserved verbatim, but their original
  # WEB source-manifest cannot certify a modified site; brand-new SHA seal below.
  qa_files={'qa/onepass_v2_original/'+n:v for n,v in qa.items()}
  from collections import Counter
  folded=[x.casefold() for x in site]
  if len(folded)!=len(set(folded)):raise ValueError('CASE_INSENSITIVE_COLLISION')
  source_shas={k:sha_file(v) for k,v in paths.items()}
  sources={'schema':'NOX-UNIFIED-WEB-SOURCE-LOCK-v27','generated_date':'2026-11-13',
    'type':'SHA256', 'sources':{k:{'sha256':source_shas[k],'bytes':paths[k].stat().st_size} for k in paths},
    'site':{k:sha(v) for k,v in sorted(site.items())},
    'qa_onepass':{k:sha(v) for k,v in sorted(qa_files.items())}}
  receipt={'schema':'NOX-WEB-WOW-V27-UNIFIED-SOURCE-CANDIDATE-v1',
    'status':'SOURCE_MERGED_CRC_SHA_STATIC_QA_PENDING_WINDOWS_E07_HOLD','production_modified':False,
    'windows_onehost_live_tested':False,'s03_rollback_tested':False,'gpu_weights_trained':False,
    'onepass_original_qa_executed_on_merged_site':False,'release_accepted':False,
    'files_site':len(site),'original_web_identical':original_unchanged,'original_web_total':len(web),
    'preserved_original_web_pages':['original_web_v25_1/chat.html','original_web_v25_1/memory.html'],
    'pc25_files':len(pc25),'pc24_whisper_fallback_files':len(extra),
    'v24_whisper_fallback_names':extra,'original_onepass_qa_files':len(qa),
    'genesis_pages_injected':{p:{'pre_sha256':old_pages[p],'post_sha256':sha(site[p])} for p in PAGES},
    'rewritten_pc_asset_count':len(rewrites),'rewritten_pc_assets':rewrites,
    'removed_public_vendor_key_only':list(sanitized),
    'original_d02_sha256':sha(web['index.html']), 'merged_d02_sha256':sha(site['index.html']),
    'input_sources':{k:{'sha256':source_shas[k],'bytes':paths[k].stat().st_size} for k in paths},
    'no_duplicate_backend':True,'one_active_noX':True,'auth_boundary_preserved':True,
    'report_timestamp':'2026-11-13',
    'physical_source_qa_requirements':['ZIP CRC','all site sha256','OneHost HTTP','WebView2 effects','Ollama stream/STOP','S03 after restart','Windows E07 same BuildID/EXE SHA']}
  runtime={}
  # Only active program code, never .bak / .db / model binaries / user data.
  app_root='NOX_CHAT_V24/app/'
  for n,data in a.items():
    if n.startswith(app_root) and (n.endswith(('.py','.json')) and '/__pycache__/' not in n):
      # No secrets; keep same original source so installed host is traceable.
      if any(p.search(data) for p in PATS.values()):
        raise ValueError('RUNTIME_REFERENCE_POTENTIAL_SECRET '+n)
      runtime['runtime_source_only/'+n[len(app_root):]]=data
  docs={
   'qa/QA_SCOPE_RU.md':('NOX V27 · ПРОВЕРКА ИЗОЛИРОВАННЫХ ИСХОДНИКОВ\n'
      'Это исходный WEB+PC чат, а не установленный Windows EXE.\n'
      'Ни один из десяти оригинальных ONEPASS файлов не может автоматически принять обновлённый SourceLock.\n'
      'GENESIS отображает HOLD до явного authenticated OneHost endpoint.\n'
      'Запрещено переносить оригинальные веса и S03 посредством этого ZIP или удалять старые файлы.\n').encode(),
   'READ_ME_FIRST_RU.md':('NOX HELION WEB WOW V27 · ONE WEB SOURCE CANDIDATE\n\n'
      'Оригинальный HOME D02 не изменён. CHAT V25/Memory S03 перенесены в site/pc/.\n'
      '7 локальных Whisper файлов взяты из V24, 10 QA скриптов ONEPASS сохранены без дублей.\n'
      'source_lock содержит SHA256 каждого файла сайта и QA.\n'
      'runtime_source_only содержит ТОЛЬКО исходники текущего backend, НЕ запускайте второй сервер.\n'
      'Без независимой Windows/OneHost E07 и проверки GPU релиз остаётся HOLD.\n').encode()
  }
  # Executable QA code and Windows-only preflight are staged, never automatically run.
  docs['qa/verify_nox_v27.py']=(root/'nox_unified_source/tools/verify_nox_v27.py').read_bytes()
  docs['qa/NOX_V27_WINDOWS_PREFLIGHT.ps1']=(root/'nox_unified_source/NOX_V27_WINDOWS_PREFLIGHT.ps1').read_bytes()
  docs['qa/STATIC_REFERENCE_QA.json']=(root/'nox_unified_source/STATIC_REFERENCE_QA.json').read_bytes()
  other={**qa_files,**runtime,**docs,
    'NOX_V27_SOURCE_LOCK.json':(json.dumps(sources,ensure_ascii=False,indent=2)+'\n').encode(),
    'NOX_V27_BUILD_RECEIPT.json':(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode()}
  out.parent.mkdir(parents=True,exist_ok=True)
  try:
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
      for n,payload in sorted(site.items()):zip_write(z,'site/'+n,payload)
      for n,payload in sorted(other.items()):zip_write(z,n,payload)
    with zipfile.ZipFile(out) as verify:
      bad=verify.testzip()
      if bad:raise ValueError('ZIP_CRC_FAILED: '+bad)
      for n,b in site.items():
        if sha(verify.read('site/'+n))!=sources['site'][n]:
          raise ValueError('ZIP_CONTENT_SHA_MISMATCH '+n)
      for n,b in qa_files.items():
        if sha(verify.read(n))!=sha(b):raise ValueError('ONEPASS_QA_SHA_MISMATCH '+n)
    receipt['final_zip_sha256']=sha_file(out)
    receipt['final_zip_bytes']=out.stat().st_size
    receipt['final_zip_members']=len(site)+len(other)
    return receipt
  except BaseException:
    out.unlink(missing_ok=True)
    raise

if __name__=='__main__':
  a=argparse.ArgumentParser();a.add_argument('--source',type=Path,default=BASE)
  a.add_argument('--out',type=Path,default=BASE/OUTPUT)
  a.add_argument('--genesis',type=Path,default=BASE/'nox_unified_source/nox_genesis_live_panel.mjs')
  args=a.parse_args()
  try:print(json.dumps(build(args.source,args.out,args.genesis),ensure_ascii=False,indent=2))
  except Exception as exc:print('NOX_V27_HOLD',type(exc).__name__,str(exc),file=sys.stderr);sys.exit(2)
