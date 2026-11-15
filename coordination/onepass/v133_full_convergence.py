"""NOX V133 converged source: canonical frozen + PR281 graphic choices + V122 + V132.

No live services, weights, S03, STOP or runtime code changed; no second backend.
Exactly 9 frozen HTML/JS files modified in derived staging and original bytes
are available for rollback; one new graphical-choice JS is included.
"""
from __future__ import annotations
import argparse,hashlib,json,re,zipfile
from pathlib import Path

FROZEN_SHA='166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0'
DERIVED_SHA='e70f0439fdf0a028c1d52fc638a38086aa7863fb7b33733a9609532dd544a9d5'
CHOICE_SHA='a6874e9f84dd92ee3c1ea9261efe45415fdde084280fc93ef63d57832e387395'
OWNER_SHA='18d8c8d6009323188b9f903920308b3b871a6123f7b425a77184a6b2c147640e'
V132_SHA='6e13a5b63607acfd2f3a1890dec33bd10c6f3ee7add59b84ef82c628e162da77'
KIT_SHA='b5540b559d9e8d117838fbde54efa2ed60e69cfee2e26266616b12d4a9eb28a4'
CHOICE_HTML={
 'site/pc/pages/cinema/index.html', 'site/pc/pages/games/index.html',
 'site/pc/pages/graph/index.html', 'site/pc/pages/music/index.html',
 'site/pc/pages/voice/index.html'
}
HTML_BASE={
 'site/pc/v22/resonance.template.html':'../',
 'site/reference/pc-original-memory.html':'../pc/',
 'site/reference/pc-original-resonance.html':'../pc/'
}
OWNER='site/nox-ui.js';NEW='site/pc/nox-choice-buttons-v293.js'
CHANGED=CHOICE_HTML|set(HTML_BASE)|{OWNER}
AUX={
 'NOX_WEB_V293_REPO_DERIVED_MANIFEST.json':'integration/NOX_WEB_V293_REPO_DERIVED_MANIFEST.json',
 'NOX_WEB_V293_92_CONTRACTS.json':'integration/NOX_WEB_V293_92_CONTRACTS.json',
 'NOX_WEB_V293_RELEASE_GATE.md':'integration/NOX_WEB_V293_RELEASE_GATE.md',
 'NOX_WEB_V293_CHROMIUM_CHOICES_QA.json':'integration/NOX_WEB_V293_CHROMIUM_CHOICES_QA.json'
}
INTEGRATION='integration/NOX_HELION_V132_ONEPASS_SAFE_SOURCE_20261115.zip'
MANIFEST='NOX_V133_CONVERGED_1090_WEB_ASSET_MANIFEST.json'
README='NOX_V133_CONVERGED_README_RU.md'
STAMP=(2026,11,15,0,0,0)
COMPRESSED={'.jpg','.jpeg','.png','.webp','.gif','.hdr','.woff','.woff2','.wasm','.zip','.mp3','.mp4','.ogg','.webm','.glb','.fbx','.ktx2','.gz','.pdf'}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def shafile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def put(z,name,raw):
 if not name or name.startswith('/') or '..' in Path(name).parts or '\\' in name:
  raise ValueError('HOLD_OUTPUT_UNSAFE_NAME')
 zi=zipfile.ZipInfo(name,STAMP)
 zi.create_system=3;zi.external_attr=0o100644<<16
 zi.compress_type=zipfile.ZIP_STORED if Path(name).suffix.lower() in COMPRESSED else zipfile.ZIP_DEFLATED
 z.writestr(zi,raw)

def make(frozen,derived,kit,owner,v132,out):
 pins=((frozen,FROZEN_SHA),(derived,DERIVED_SHA),(kit,KIT_SHA),(owner,OWNER_SHA),(v132,V132_SHA))
 for name,expected in pins:
  if not name.is_file() or shafile(name)!=expected:
   raise ValueError('HOLD_INPUT_SHA_'+name.name)
 if out.exists():raise ValueError('HOLD_OUTPUT_ALREADY_EXISTS')
 overlay=owner.read_bytes();v132_data=v132.read_bytes()
 row=[];modifications=[]
 with zipfile.ZipFile(frozen) as original,zipfile.ZipFile(derived) as choices,zipfile.ZipFile(kit) as extras:
  if any(z.testzip() is not None for z in (original,choices,extras)):
   raise ValueError('HOLD_INPUT_ZIP_CRC')
  ns=original.namelist();nd=choices.namelist()
  if (len(ns)!=1089 or len(set(ns))!=1089 or len(nd)!=1090
      or set(nd)!=set(ns)|{NEW} or any(not n.startswith('site/') for n in ns)):
   raise ValueError('HOLD_FROZEN_DERIVED_SET')
  for n in ns:
   a=original.read(n);b=choices.read(n)
   if (a!=b)!=(n in CHOICE_HTML):raise ValueError('HOLD_FOREIGN_DERIVED_DIFF_'+n)
  if sha(choices.read(NEW))!=CHOICE_SHA:
   raise ValueError('HOLD_CHOICE_SCRIPT_SHA')
  with zipfile.ZipFile(out,'x',allowZip64=True) as z:
   for name in ns:
    raw=original.read(name)
    if name in CHOICE_HTML: dest=choices.read(name);origin='PR281_GRAPHIC_BUTTONS'
    elif name==OWNER:dest=overlay;origin='OWNER_V122_VERIFIED'
    elif name in HTML_BASE:
     old=raw.decode('utf8')
     if len(re.findall(r'<head\b[^>]*>',old,re.I))!=1 or re.search(r'<base\b',old,re.I):
      raise ValueError('HOLD_LEGACY_BASE_SOURCE_DRIFT')
     tag='<base href="'+HTML_BASE[name]+'">'
     dest=re.sub(r'<head\b[^>]*>',lambda m:m.group()+tag,old,count=1,flags=re.I).encode('utf8')
     origin='NOLOSS_LEGACY_RELATIVE_BASE'
    else:dest=raw;origin='ORIGINAL_FROZEN'
    put(z,name,dest)
    change=dest!=raw
    if change:
     if name not in CHANGED:raise ValueError('HOLD_UNEXPECTED_CHANGE')
     put(z,'rollback/'+name,raw)
     modifications.append(name)
    row.append({'path':name,'source_sha256':sha(raw),'candidate_sha256':sha(dest),
                'source_bytes':len(raw),'candidate_bytes':len(dest),'changed':change,
                'provenance':origin})
   put(z,NEW,choices.read(NEW))
   put(z,INTEGRATION,v132_data)
   for x,y in AUX.items():put(z,y,extras.read(x))
   readme='''NOX V133 · единый WEB V29.3 на реальных 1 089 frozen исходниках\n\n9 изменённых исходных файлов: 5 страниц графических кнопок PR281, owner V122 nox-ui.js, 3 legacy HTML base href. Каждый исходник хранится в rollback/site/...\n1 добавленный рабочий JavaScript выбора: site/pc/nox-choice-buttons-v293.js (source PR281).\nВсе 1 089 оригинальных путей сохранены, остальные 1 080 файлов байтово неизменны; не создавалась новая база или backend.\nИнтеграция V132 включает строго привязанный к исходной S03 owner fact writer, offline tests и Windows V70 инструменты.\nЭто STAGING кандидат, а не разрешение переключить production: Vast NOX2 auth_error, старый SSH route ConnectionRefused.\nДо установки обязательны: реальный owner auth, SHA одного существующего OneHost, backup+rollback, STOP, readback S03, browser Windows and full training/restore acceptance.\nПоследняя реальная проверка OneHost: 23/92 напрямую зарегистрированных WEB API, 69 без точного URL совпадения. Недостающие функции нельзя имитировать 200/READY.\nONEPASS 65 исходных тестов PASS; визуальный Chromium QA графических выборов из пакета PR281 — отдельно, backend НЕ проверен.\n\nОригинал frozen ZIP SHA256: '''+FROZEN_SHA+'\n'
   put(z,README,readme.encode('utf8'))
   manifest={'schema':'NOX_V133_CONVERGED_FULL_WEB_V293_V1',
      'frozen_sha256':FROZEN_SHA,'derived_ui_sha256':DERIVED_SHA,
      'pr281_choice_script_sha256':CHOICE_SHA,'owner_v122_script_sha256':OWNER_SHA,
      'v132_integration_sha256':V132_SHA,
      'original_file_count':1089,'original_paths_preserved':1089,
      'original_files_changed':len(modifications),'original_files_unchanged':1089-len(modifications),
      'original_files_deleted':0,'new_original_site_assets':1,
      'changed_paths':sorted(modifications),'choice_pages':sorted(CHOICE_HTML),
      'original_v29_web_92_api_fully_functional':False,
      'owner_windows_physical_qa':False,'native_production_deployed':False,
      'real_optimizer_checkpoint_verified':False,'no_new_backend':True,
      'no_private_data':True,'source_files':row}
   put(z,MANIFEST,(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode())
 return verify(out)

def verify(path):
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None:raise ValueError('HOLD_CANDIDATE_CRC')
  manifest=json.loads(z.read(MANIFEST))
  if manifest.get('original_file_count')!=1089 or manifest.get('original_files_changed')!=9:
   raise ValueError('HOLD_CANDIDATE_COUNT')
  required={r['path'] for r in manifest['source_files']}|{'rollback/'+n for n in CHANGED}|{NEW,INTEGRATION,README,MANIFEST}|set(AUX.values())
  names=z.namelist()
  if len(names)!=len(required) or set(names)!=required:raise ValueError('HOLD_CANDIDATE_MEMBERS')
  for row in manifest['source_files']:
   name=row['path'];data=z.read(name)
   if sha(data)!=row['candidate_sha256'] or len(data)!=row['candidate_bytes']:
    raise ValueError('HOLD_CANDIDATE_ASSET_SHA_'+name)
   if name in CHANGED and sha(z.read('rollback/'+name))!=row['source_sha256']:
    raise ValueError('HOLD_CANDIDATE_ROLLBACK_SHA_'+name)
  if sha(z.read(NEW))!=CHOICE_SHA or sha(z.read(INTEGRATION))!=V132_SHA:
   raise ValueError('HOLD_CANDIDATE_INTEGRATION_SHA')
  return {'state':'CONVERGED_FULL_WEB_STAGING_SHA_CRC_PASS',
          'zip':path.name,'bytes':path.stat().st_size,'sha256':shafile(path),
          'frozen_paths':1089,'changed_original_paths':9,'unchanged_original_paths':1080,
          'original_files_deleted':0,'new_live_choice_script':1,
          'owner_v122_pinned':True,'pr281_buttons_merged':True,
          'v132_embedded':True,'production_deployed':False,'native_92_e2e_accepted':False}

def main():
 p=argparse.ArgumentParser()
 for n in ('frozen','derived','kit','owner','v132','out'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args()
 print(json.dumps(make(a.frozen,a.derived,a.kit,a.owner,a.v132,a.out),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
