#!/usr/bin/env python3
"""One active NOX WEB source build: V140 primary + 5 worlds + Motion100 + 2K assets + media chat.
Historical rollback/delta-only versions are excluded from the DISTRIBUTION ZIP, not deleted at source.
"""
from pathlib import Path
import hashlib,json,re,zipfile,os

W=Path('/mnt/data/nox_unified_build');AS=W/'assets'
V140=AS/'NOX_HELION_WEB_V29_3_UNIFIED_ALL_HISTORY_20261115.zip'
WORLDS=AS/'NOX_HELION_WEB_5_WORLDS_6_COLORS_ONEPACK_20261116.zip'
MOTION=AS/'NOX_WEB29_3D_MOTION100_SAFE_OVERLAY_20261116.zip'
VISUAL=AS/'NOX_DRIVE_ORIGINAL_LIBRARIES_VISUAL_PATCH_20261116.zip'
FROZEN=Path('/mnt/data/NOX_HELION_WEB_V29_3_FROZEN_20261113.zip')
FINAL=Path('/mnt/data/NOX_HELION_WEB_UNIFIED_RESONANCE_MEDIA_20261116.zip');TMP=FINAL.with_suffix('.pending.zip')
PIN={V140:'cf5a4bbec37a4224a03f814f6c89d3417d6406dac03dfdea2085689295492826',
     WORLDS:'92c2493ce6459aa3e925f7f6e01aac6030e4f52d585f12378d8e5692f47735d5',
     MOTION:'18cb2692cf2c2be454d38778f20fced899f92d8608919446e17f43104cd10e0b',
     VISUAL:'6293753f6bce58cfd5295aaf11326ef91a2b49ca755a41bb33994fb03870f52f',
     FROZEN:'166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0'}

def sha(v):return hashlib.sha256(v).hexdigest()
def fsha(p):
 h=hashlib.sha256()
 with p.open('rb') as r:
  for b in iter(lambda:r.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 for p,pin in PIN.items():
  if fsha(p)!=pin:raise RuntimeError('HOLD_SOURCE_PIN_'+p.name)
 with zipfile.ZipFile(V140) as v, zipfile.ZipFile(WORLDS) as w,zipfile.ZipFile(MOTION) as m,zipfile.ZipFile(VISUAL) as vis,zipfile.ZipFile(FROZEN) as fr:
  for p,z in [('V140',v),('worlds',w),('Motion',m),('visual',vis),('Frozen',fr)]:
   if z.testzip() is not None or len(z.namelist())!=len(set(z.namelist())):raise RuntimeError('HOLD_INPUT_ZIP_'+p)
  v140={x:v.read(x) for x in v.namelist()}
  worlds={x:w.read(x) for x in w.namelist()}
  frozen={x:fr.read(x) for x in fr.namelist()}
  if len(v140)!=1162 or len(worlds)!=1101 or len(frozen)!=1089 or not set(frozen).issubset(v140):raise RuntimeError('HOLD_INPUT_BASE_COMPLETENESS')
  # Deliberately strip older source-version deltas and backups from the ONLY distributable WEB ZIP.
  # Their source archive remains intact in owner Library for rollback until actual native acceptance.
  excluded=lambda p: p.startswith(('rollback/','support/')) or p=='integration/NOX_HELION_V132_ONEPASS_SAFE_SOURCE_20261115.zip'
  active={p:raw for p,raw in v140.items() if not excluded(p)}
  active_baseline={p:raw for p,raw in active.items() if p.startswith('site/')}
  changes={};new={}
  def add(p,content,reason,allow_change=False):
   if '..' in p.split('/') or p.startswith('/') or '\\' in p:raise RuntimeError('HOLD_UNSAFE_PATH_'+p)
   if p in active:
    if active[p]==content:return
    if not allow_change:raise RuntimeError('HOLD_UNEXPECTED_REPLACE_'+p)
    changes.setdefault(p,{'prior_sha256':sha(active[p]),'reason':reason})
   else:new[p]=reason
   active[p]=content
  def inject(p,tags,reason):
   value=active[p]
   if value.count(b'</head>')!=1:raise RuntimeError('HOLD_HEAD_'+p)
   for tag in tags:
    if tag in value:raise RuntimeError('HOLD_DUPLICATE_TAG_'+p)
   add(p,value.replace(b'</head>',b'\n'+b'\n'.join(tags)+b'\n</head>',1),reason,True)
  # 5 worlds: preserve V140 page content and native fixes; port ONLY the four new additive asset tags.
  for p,blob in worlds.items():
   if p not in active:
    if p.startswith('site/'):
     add(p,blob,'5_world_6_palette_assets')
  world_tags={}
  pattern=re.compile(rb'<(?:script|link)\b[^>]*\bdata-nox-(?:wow-max|five-worlds)="[^"]+"[^>]*>(?:</script>)?',re.I)
  for p,raw in worlds.items():
   if not p.endswith('.html') or p not in active or p not in frozen or raw==frozen[p]:continue
   tags=pattern.findall(raw)
   if not tags:raise RuntimeError('HOLD_WORLD_PAGE_TAGS_'+p)
   # Only one of each functional world tag is added to current V140 pages.
   unique=[]
   for tag in tags:
    if tag not in unique and tag not in active[p]:unique.append(tag)
   if unique:
    inject(p,unique,'5_world_6_palette_html_overlay')
    world_tags[p]=len(unique)
  if len(world_tags)<25:raise RuntimeError('HOLD_FIVE_WORLDS_PAGE_COVERAGE')
  # Original Drive visual upgrade. Preserve source identity (no HTML/server changes).
  for path in vis.namelist():
   blob=vis.read(path)
   if path in ('README_ORIGINAL_DRIVE_ASSETS.md','NOX_DRIVE_ORIGINALS_INSTALL_V2.json'):
    add('integration/source-assets/'+path,blob,'original_visual_source_manifest');continue
   target='site/'+path
   if target in active and active[target]!=blob:
    if not target.endswith(('.mjs','.css')):raise RuntimeError('HOLD_VISUAL_CONFLICT_'+target)
    if target in frozen and active[target]!=frozen[target]:raise RuntimeError('HOLD_VISUAL_SOURCE_DRIFT_'+target)
    add(target,blob,'2K_visual_modules',True)
   else:add(target,blob,'2K_visual_assets')
  # Motion100 sources, no outdated HTML overwrite.
  for name in m.namelist():
   if name.startswith('site/motion100/') or name in ('site/nox-motion-idle-loader.js','site/nox-cinematic-accessibility-3d.css'):
    add(name,m.read(name),'motion100_assets')
  add('integration/motion100_original_manifest.json',m.read('MANIFEST.json'),'motion100_source_manifest')
  # Current V140 already carries V135/137 native JS. Keep its newer V137 implementation.
  for p in ('site/nox-v135-resonance-owner-bridge.js','site/nox-v137-owner-self-status.js',
            'integration/nox_v137_owner_self_observation.py','integration/nox_v137_owner_response_contract.py'):
   if p not in active:raise RuntimeError('HOLD_V140_NATIVE_BRIDGE_MISSING_'+p)
  if b'/api/nox/chat/stream' not in active['site/nox-v135-resonance-owner-bridge.js']:
   raise RuntimeError('HOLD_V135_NATIVE_STREAM')
  # One new media front end bound to existing authenticated OneHost; no new backend.
  add('site/nox-media-chat.js',(W/'nox-media-chat.js').read_bytes(),'media_in_resonance')
  add('site/nox-media-chat.css',(W/'nox-media-chat.css').read_bytes(),'media_in_resonance')
  media_tags={
   'site/chat.html':[
     b'<link rel="stylesheet" href="./nox-media-chat.css" data-nox-media="1">',
     b'<link rel="stylesheet" href="./nox-cinematic-accessibility-3d.css" data-nox-3d="1">',
     b'<script defer src="./nox-motion-idle-loader.js" data-nox-idle="1"></script>',
     b'<script defer src="./nox-media-chat.js" data-nox-media="1"></script>'],
   'site/pc/resonance.html':[
     b'<link rel="stylesheet" href="/nox-web-v29/nox-media-chat.css" data-nox-media="1">',
     b'<link rel="stylesheet" href="/nox-web-v29/nox-cinematic-accessibility-3d.css" data-nox-3d="1">',
     b'<script defer src="/nox-web-v29/motion100/nox-motion100-lazy.js" data-nox-motion100="1"></script>',
     b'<script defer src="/nox-web-v29/nox-media-chat.js" data-nox-media="1"></script>'],
   'site/pc/v22/resonance.template.html':[
     b'<link rel="stylesheet" href="/nox-web-v29/nox-media-chat.css" data-nox-media="1">',
     b'<script defer src="/nox-web-v29/nox-media-chat.js" data-nox-media="1"></script>'],
  }
  for p,tags in media_tags.items():inject(p,tags,'single_media_chat')
  receipt={
    'schema':'NOX_HELION_WEB_SINGLE_UNIFIED_V140_MEDIA_WORLDS_20261116',
    'instructions_version':'0.0.6','built':'2026-11-16','status':'SOURCE_VERIFIED_NATIVE_HOLD',
    'primary_web':'/nox-web-v29/pc/resonance.html','one_zip':'NOX_HELION_WEB_UNIFIED_RESONANCE_MEDIA_20261116.zip',
    'sources':{p.name:pin for p,pin in PIN.items()},
    'v140_base_included':True,'v140_active_site_retained':len(active_baseline),
    'world_palette_html_pages_patched':len(world_tags),'motion_svg_count':sum(p.startswith('site/motion100/svg/') and p.endswith('.svg') for p in active),
    'historical_rollback_and_superseded_deltas_excluded_from_new_distribution':True,
    'historical_rollback_preserved_in_original_library_v140_archive':True,
    'old_external_builds_deleted':False,
    'current_no_second_backend':True,'native_media_module_reference':'https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/81a8311962404e956703eb5aa49e4b77a0a01bba/nox-control/owner_media_runtime.py',
    'media_api':'/api/ui/media','current_photo_video_generation_on_real_v100_verified':False,
    'image_video_editing_native_verified':False,'S03_weights_checkpoints_modified':False,
    'source_changed_files':changes,'source_added_files':new,
    'native_gpu_model_install':'NOT_PERFORMED',
    'native_acceptance':'HOLD_OWNER_COOKIE_S03_STOP_GPU_AND_MEDIA_E2E'
  }
  add('NOX_ONE_FINAL_SOURCE_RECEIPT.json',(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode(),'one_source_receipt')
  add('NOX_README_FIRST.txt',(
    'NOX HELION ONE UNIFIED WEB SOURCE · 16 NOV 2026\n'
    'Source base: V140 owner stream + V137 (read from owner Library), with worlds5/colors6, Motion100, 2K original visuals, media chat.\n'
    'One primary chat /nox-web-v29/pc/resonance.html\n'
    'Existing native OneHost must serve /api/ui/media and owner-auth, and install ComfyUI + valid image/video checkpoints. No native model downloaded by this ZIP.\n'
    'Local GPU generation, image/video editing, native STOP and full S03 readback are NOT accepted from this source-only package.\n'
    'Old rollback and superseded source copies are excluded from this distribution; the original Library V140 archive is retained for rollback.\n'
    'Never delete S03, model weights, checkpoints, optimizer, or the only running service.\n').encode(),'one_readme')
  if TMP.exists():TMP.unlink()
  with zipfile.ZipFile(TMP,'x',allowZip64=True,compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
   for p,content in active.items():
    info=zipfile.ZipInfo(p,date_time=(2026,11,16,20,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
    z.writestr(info,content)
  with zipfile.ZipFile(TMP) as z:
   names=z.namelist()
   if z.testzip() is not None or len(names)!=len(set(names)):raise RuntimeError('HOLD_OUTPUT_CRC')
   if set(active_baseline)!=set(p for p in names if p in active_baseline):raise RuntimeError('HOLD_V140_ACTIVE_SITE_LOSS')
   if not all(p in names for p in worlds if p.startswith('site/') and p not in frozen):raise RuntimeError('HOLD_WORLD_ASSET_LOSS')
   if sum(p.startswith('site/motion100/svg/') and p.endswith('.svg') for p in names)!=100:raise RuntimeError('HOLD_MOTION100')
   for p,content in active.items():
    if sha(z.read(p))!=sha(content):raise RuntimeError('HOLD_FILE_READBACK_'+p)
   for p in media_tags:
    if not all(t in z.read(p) for t in media_tags[p]):raise RuntimeError('HOLD_MEDIA_INJECTION_'+p)
  evidence={
    'SHA256':fsha(TMP),'bytes':TMP.stat().st_size,'zip_entries':len(active),
    'preserved_active_v140_site_paths':len(active_baseline),'v140_total_input_paths':len(v140),
    'old_superseded_backup_paths_excluded':len(v140)-len(active_baseline)-len([x for x in active if not x.startswith('site/') and x in v140]),
    'world_palette_patched_html':len(world_tags),'motion100_svg':100,
    'added_files':len(new),'modified_files':len(changes),
    'zip_crc':'PASS','native_onehost_media':'HOLD_NOT_INSTALLED_VERIFIED'
  }
  os.replace(TMP,FINAL)
  (W/'final_build_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(evidence,ensure_ascii=False,indent=2))

if __name__=='__main__':main()