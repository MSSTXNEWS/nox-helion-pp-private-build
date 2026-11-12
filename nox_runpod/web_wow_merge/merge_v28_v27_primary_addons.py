#!/usr/bin/env python3
"""Single NOX V27-first + V25 PC/additive GENESIS source merge.
No existing file/production paths touched. User-owned artwork remains byte-identical.
"""
import zipfile, os, io, re, json, hashlib, collections, sys, time
from pathlib import PurePosixPath, Path
R=Path(os.environ.get('NOX_MERGE_DIR',Path.cwd())).resolve()
MAIN=R/'NOX_WEB_V27_VERIFIED_STAGING_64053ce.zip'
PC25=R/'NOX_CHAT_V25_SOURCES_PC_20261112.zip'
PC24=R/'NOX_CHAT_V24_SOURCES_20261112.zip'
ONEPASS=R/'NOX_HELION_ONEPASS_V2_HARDENED_20261112.zip'
CHROMIUM=R/'NOX_WEB_V27_CHROMIUM_QA_64053ce.zip'
OUT=R/'NOX_HELION_WEB_V28_V27_PC_GENESIS_UNIFIED_SOURCE_20261113.zip'
EVIDENCE=R/'NOX_HELION_WEB_V28_UNIFIED_VERIFICATION.json'
HASH={'d02':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',
'pbr':'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905',
'approved_home':'3253d26819a70b49259fdb2a56c2eaa2455c6878cb2ccb8d62b225ec6ccdfa22',
'index':'f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17',
'chat':'', 'memory':''}
sha=lambda b:hashlib.sha256(b).hexdigest()
def check_safe(name):
    if not name or name.startswith('/') or '\\' in name or any(x in ('','.','..') for x in name.split('/')) or PurePosixPath(name).as_posix()!=name:raise ValueError('UNSAFE_ZIP_PATH:'+name)
def read_z(p,strip=''):
    d={};seen=set()
    with zipfile.ZipFile(p) as z:
        bad=z.testzip()
        if bad:raise ValueError(f'ZIP_CRC_HOLD:{p.name}:{bad}')
        for i in z.infolist():
            if i.is_dir():continue
            check_safe(i.filename)
            if strip and not i.filename.startswith(strip):continue
            n=i.filename[len(strip):]
            if not n:continue
            check_safe(n)
            if n.casefold() in seen:raise ValueError('WINDOWS_CASE_COLLISION:'+n)
            seen.add(n.casefold())
            if i.file_size>150000000:raise ValueError('ZIP_MEMBER_SIZE_HOLD:'+n)
            if (i.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP_SYMLINK_HOLD:'+n)
            d[n]=z.read(i)
    return d
main=read_z(MAIN)
for rel,key in [('index.html','index'),('nox-home.mjs','d02'),('nox-engines/physical-worlds-v7.mjs','pbr'),('assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp','approved_home')]:
    assert rel in main,(rel,'MISSING')
    assert sha(main[rel])==HASH[key],('APPROVED_SOURCE_DRIFT',rel,sha(main[rel]))
for page in ['index','chat','cinema','install','memory','models','projects','settings','system','training']:
    assert page+'.html' in main,'10_PAGE_CONTRACT:'+page
v27_count=len(main)
pc25=read_z(PC25,'NOX_CHAT_V24/web/')
pc24=read_z(PC24,'NOX_CHAT_V24/web/')
assert len(pc25)==743,(len(pc25),'PC25_COUNT_UNEXPECTED')
missing=set(pc24)-set(pc25)
assert len(missing)==7,(len(missing),'PC24_FALLBACK_COUNT_UNEXPECTED')
assert all('pages/_vendor/whisper-tiny/' in x for x in missing),('UNEXPECTED_PC24_FALLBACK',missing)
conflicts=[p for p in pc25 if p in main and pc25[p]!=main[p]]
assert len(conflicts)>5,'EXPECTED_DIFFERENT_PC_V25_FILES'
assert all(len(pc25.get(q,b''))>0 for q in ['resonance.html','memory.html','chat.html','index.html'])
# Keep unchanged original current site and integrate PC V25 as an additive namespace.
site=dict(main)
SENSITIVE={
 'github_pat':re.compile(rb'github_pat_[A-Za-z0-9_]{24,}'),
 'github':re.compile(rb'ghp_[A-Za-z0-9]{28,}'),
 'openai':re.compile(rb'sk-[A-Za-z0-9]{28,}'),
 'google':re.compile(rb'AIza[0-9A-Za-z_-]{30,}')}
STATIC_ABS=re.compile(rb'''(?P<q>["'])(?:/)(?P<dir>vendor|v22|v23|v24|v25|predator|assets13|assets|nox-engines|nox-worlds|pages)/''',re.I)
STATIC_INTERNAL_PAGES=re.compile(rb'''(?P<q>["'])/(?P<page>menu|world|hub)\.html''',re.I)
normalized=[];security_sanitized=[]
def clean_pc(name,data):
    orig=data
    if name=='pages/_vendor/excalidraw/excalidraw.production.min.js':
        new,n=SENSITIVE['google'].subn(b'',data)
        if n:security_sanitized.append({'path':name,'sanitized_vendor_room_keys':n,'prior_sha':sha(data)})
        data=new
    if name.endswith(('.html','.htm','.css','.js','.mjs','.json')):
        for k,pattern in SENSITIVE.items():
            if pattern.search(data):raise ValueError('SOURCE_SECRET_HOLD:'+name+':'+k)
        if name.endswith(('.html','.htm','.js','.mjs','.css')):
            data=STATIC_ABS.sub(lambda m:m.group('q')+b'/pc/'+m.group('dir')+b'/',data)
            data=STATIC_INTERNAL_PAGES.sub(lambda m:m.group('q')+b'/pc/'+m.group('page')+b'.html',data)
    if data!=orig:normalized.append({'path':'pc/'+name,'before':sha(orig),'after':sha(data)})
    return data
for n,b in pc25.items():
    name='pc/'+n
    assert name not in site,'NAMESPACE_COLLISION:'+name
    site[name]=clean_pc(n,b)
for n in sorted(missing):
    k='pc/'+n
    assert k not in site
    site[k]=clean_pc(n,pc24[n])
# Strictly preserve PC's original own HOME for rollback in documentation, but
# the ACTIVE PC/index.html redirects to the ONLY canonical V27 HOME.
pc_original_index=site['pc/index.html']
site['reference/pc-v25-original-index.html']=pc_original_index
site['pc/index.html']=b'<!doctype html><html lang="ru"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=../index.html"><title>NOX HOME</title><script>location.replace("../index.html")</script><a href="../index.html">NOX HOME</a></html>\n'
normalized.append({'path':'pc/index.html','before':sha(pc_original_index),'after':sha(site['pc/index.html']),'reason':'no second active HOME'})
# Current root pages retain original NOX V27; embed only secondary optional addon.
BRIDGE_JS=r'''/* NOX V28 additive PC/GENESIS surface. Canonical D02 and V27 route logic untouched.
 * GENESIS requires the trusted existing same-origin OneHost endpoint meta.
 * No model startup, no additional backend, no private S03 writes.
 */
const OWNER_SCHEMA='nox-genesis-live-evidence-v1';
const PAGE=document.body?.dataset?.page;
const PAGES=new Set(['chat','memory','training']);
const make=(t,c,text)=>{const n=document.createElement(t);if(c)n.className=c;if(text)n.textContent=text;return n;};
function genesisText(x){
 if(!x||x.schema!==OWNER_SCHEMA)return 'HOLD · Ответ OneHost не подтверждён';
 if(x.state==='HOLD')return 'HOLD · '+String(x.reason||'нет данных').slice(0,140);
 if(x.state!=='RECEIPT_FORMAT_VALIDATED_NOT_GPU_REPLAYED')return 'HOLD · статус обучения не подтверждён';
 const t=x.training||{};
 if(!/^[a-f0-9]{64}$/i.test(t.model_sha256||''))return 'HOLD · отсутствует SHA весов';
 const lines=['Квитанция OneHost получена — не независимая GPU-приёмка',
 'NOX SHA: '+t.model_sha256.slice(0,16)+'…',
 'Шаги optimizer (по квитанции): '+(Number.isSafeInteger(t.optimizer_steps_claimed)?t.optimizer_steps_claimed:'Н/Д'),
 'Checkpoint: '+(/^[a-f0-9]{64}$/i.test(t.checkpoint_sha256||'')?t.checkpoint_sha256.slice(0,16)+'…':'HOLD'),
 'S03: '+(x.memory?.state==='CONNECTED_BY_TRUSTED_HOST'?'связь по квитанции':'HOLD')];
 return lines.join('\n');
}
function endpoint(){
 const raw=document.querySelector('meta[name="nox-genesis-evidence-endpoint"]')?.getAttribute('content');
 if(!raw||!raw.startsWith('/')||raw.startsWith('//')||/[?#]/.test(raw))return null;
 try{const u=new URL(raw,location.href);return u.origin===location.origin?u.href:null}catch{return null}
}
async function readEvidence(){
 const url=endpoint();if(!url)return {schema:OWNER_SCHEMA,state:'HOLD',reason:'действующий OneHost не предоставил endpoint'};
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
 try{
  const r=await fetch(url,{credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,headers:{Accept:'application/json'}});
  if(!r.ok)return {schema:OWNER_SCHEMA,state:'HOLD',reason:'HTTP '+r.status};
  if(Number(r.headers.get('content-length')||0)>250000)throw Error('oversize');
  const data=await r.text();if(data.length>250000)throw Error('oversize');return JSON.parse(data);
 }catch{return {schema:OWNER_SCHEMA,state:'HOLD',reason:'нет подтверждённого ответа OneHost'}}finally{clearTimeout(timer)}
}
function boot(){
 if(!PAGES.has(PAGE)||document.getElementById('nox-v28-addons'))return;
 const area=make('section','nox-v28-addons');area.id='nox-v28-addons';area.setAttribute('aria-label','Дополнительные возможности NOX');
 const caption=make('span','nox-v28-caption','NOX · ДОПОЛНИТЕЛЬНЫЕ ИНСТРУМЕНТЫ');area.append(caption);
 const actions=make('div','nox-v28-actions');area.append(actions);
 const aux=[['chat','pc/resonance.html','PC CHAT · ДОПОЛНЕНИЕ'],['memory','pc/memory.html','PC MEMORY · ДОПОЛНЕНИЕ']];
 for(const [page,url,title] of aux){if(page!==PAGE)continue;const a=make('a','nox-v28-link',title);a.href=url;a.setAttribute('title','Существующий PC V25. Требует OneHost; не заменяет основной NOX WEB.');actions.append(a)}
 const button=make('button','nox-v28-button','GENESIS · ПРОВЕРИТЬ');button.type='button';button.setAttribute('aria-expanded','false');actions.append(button);
 const panel=make('div','nox-v28-panel');panel.hidden=true;panel.setAttribute('role','status');panel.setAttribute('aria-live','polite');
 const info=make('pre','','HOLD · нет проверенных данных OneHost');panel.append(info);
 const reload=make('button','nox-v28-button','Обновить доказательства');reload.type='button';panel.append(reload);area.append(panel);
 const check=async()=>{button.disabled=true;reload.disabled=true;try{info.textContent=genesisText(await readEvidence())}finally{button.disabled=false;reload.disabled=false}};
 button.addEventListener('click',()=>{panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)void check();});reload.addEventListener('click',check);
 const target=document.querySelector('main')||document.querySelector('.shell')||document.body;
 target.prepend(area);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
'''
BRIDGE_CSS=r'''/* NOX approved volcanic/obsidian secondary only — no HOME changes */
.nox-v28-addons{position:relative;z-index:12;width:min(100%,950px);margin:8px auto 12px;padding:10px 13px;background:linear-gradient(135deg,rgba(8,11,17,.94),rgba(30,21,13,.91));border:1px solid rgba(188,138,75,.45);border-radius:13px;box-shadow:inset 0 1px rgba(255,255,255,.08),0 8px 23px #0006;box-sizing:border-box;color:#e9c998}
.nox-v28-caption{font:600 10px/1.25 system-ui,sans-serif;letter-spacing:.14em;color:#c4a277;display:block;margin:0 0 7px}
.nox-v28-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.nox-v28-link,.nox-v28-button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:9px 13px;border:1px solid #af865066;border-radius:10px;color:#f4d5ab;background:linear-gradient(160deg,#30271ff0,#12151af0);box-shadow:inset 0 1px #fff1;text-decoration:none;font:600 12px/1.25 system-ui,sans-serif;cursor:pointer;transition:box-shadow .18s ease,filter .18s ease}
.nox-v28-link:hover,.nox-v28-button:hover{box-shadow:inset 0 1px #fff2,0 0 16px #d38c2440;filter:brightness(1.12)}
.nox-v28-link:focus-visible,.nox-v28-button:focus-visible{outline:2px solid #f0b66b;outline-offset:3px}
.nox-v28-panel{margin:10px 0 0;padding:10px;background:rgba(0,0,0,.40);border-radius:10px;border:1px solid #87623c66}
.nox-v28-panel[hidden]{display:none}.nox-v28-panel pre{font:12px/1.6 ui-monospace,Consolas,monospace;color:#f2d7b9;white-space:pre-wrap;overflow-wrap:anywhere}
.nox-v28-button:disabled{cursor:wait;opacity:.65}
@media(max-width:560px){.nox-v28-addons{margin:4px 6px 10px;width:calc(100% - 12px)}.nox-v28-actions>*{flex:1 1 160px;min-height:44px}}
@media(prefers-reduced-motion:reduce){.nox-v28-addons *{transition:none!important;animation:none!important}}
'''
site['nox-v28-pc-genesis-addons.mjs']=BRIDGE_JS.encode('utf8');site['nox-v28-pc-genesis-addons.css']=BRIDGE_CSS.encode('utf8')
mutations=[]
for page in ['chat.html','memory.html','training.html']:
    old=site[page]
    assert old.count(b'</body>')==1,'BODY_TAG_AMBIGUOUS:'+page
    inject=b'<link rel="stylesheet" href="./nox-v28-pc-genesis-addons.css"><script type="module" src="./nox-v28-pc-genesis-addons.mjs"></script>\n'
    assert inject not in old
    new=old.replace(b'</body>',inject+b'</body>',1)
    mutations.append({'path':page,'before_sha256':sha(old),'after_sha256':sha(new),'delta':'one additive CSS and JS import'})
    site[page]=new
# Make the original PC secondary pages able to return to canonical V27, without
# ever invoking the PC's older index HOME; keep originals as source references.
for page,destination,label in [('pc/resonance.html','../chat.html','РЕЗОНАНС · ГЛАВНЫЙ ЧАТ'),('pc/memory.html','../memory.html','ПАМЯТЬ · ГЛАВНАЯ S03')]:
    old=site[page];m=re.search(rb'<body\b[^>]*>',old,re.I)
    assert m,'PC_BODY_TAG_MISSING:'+page
    nav=('<div class="nox-v28-pc-return" style="position:relative;z-index:99;display:flex;justify-content:flex-end;padding:6px 12px;background:#09090bf0;border-bottom:1px solid #85613c88"><a href="'+destination+'" style="display:inline-flex;min-height:44px;align-items:center;padding:7px 13px;color:#f0c68e;background:#211b17;border:1px solid #a07a45;border-radius:9px;font:600 12px system-ui,sans-serif;text-decoration:none">'+label+'</a></div>').encode('utf8')
    new=old[:m.end()]+nav+old[m.end():]
    site['reference/pc-original-'+page.split('/')[-1]]=old
    site[page]=new
    mutations.append({'path':page,'before_sha256':sha(old),'after_sha256':sha(new),'delta':'add only canonical return navigation'})
# OnePass original QA: original 10 entries, no second WEB copy.
qa=read_z(ONEPASS)
assert sum(1 for n in qa if n.startswith('site/'))==292
countqa=0
for n,b in qa.items():
    if n.startswith('site/'):continue
    site['qa/onepass_v2_original/'+n]=b;countqa+=1
assert countqa==10,countqa
# Full, immutable historical V27 browsing evidence, not a claim of new hardware QA.
prior_qa=read_z(CHROMIUM)
for n,b in prior_qa.items():
    site['qa/v27_browser/'+n]=b
# The QA receipt is independent evidence from actual HTTP + isolated Chromium
# component interactions. It explicitly does NOT claim full V28 E2E or hardware.
qa28=R/'NOX_WEB_V28_STATIC_AND_DOM_QA.json'
if qa28.exists():
    report=json.loads(qa28.read_text('utf8'))
    assert report['acceptance']=='SOURCE_AND_ADDON_DOM_QA_PASS_NOT_NATIVE_RELEASE'
    assert report['live_http_200_checks']==15
    site['qa/v28_cross_source_static_and_dom_report.json']=qa28.read_bytes()
    qa_script=R/'test_nox_v28_static_dom.py'
    if qa_script.is_file():site['qa/v28_static_dom_test_source.py']=qa_script.read_bytes()
    site['qa/v28_merge_builder_source.py']=Path(__file__).read_bytes()
# Static 10+addon routes and provenance. No duplicate v25 active root/index.
index_unchanged=(sha(site['index.html'])==HASH['index'])
assert index_unchanged
assert site['nox-home.mjs']==main['nox-home.mjs']
assert site['nox-engines/physical-worlds-v7.mjs']==main['nox-engines/physical-worlds-v7.mjs']
assert site['nox-chat.js']==main['nox-chat.js']
assert site['nox-function-catalog.js']==main['nox-function-catalog.js']
assert site['nox-function-catalog.css']==main['nox-function-catalog.css']
assert site['nox-ui.js']==main['nox-ui.js']
assert all(site[n]==main[n] for n in main if n not in ['chat.html','memory.html','training.html'])
# Cross-folder names must be unique under Windows case-insensitive behavior.
casekeys={}
for p in site:
  if p.casefold() in casekeys:raise ValueError('FINAL_CASE_COLLISION:'+p)
  casekeys[p.casefold()]=p
# Keep exact sources, all modules; no active legacy V25 home/index file at site root.
receipt={
 'schema':'NOX_WEB_V28_V27_PRIMARY_PC_V25_GENESIS_ADDITIVE_SOURCE_V1',
 'date_utc':'2026-11-13',
 'primary':{'github_pr':241,'head_sha':'64053cead613ab646f7dcf05ea68479bab8bf434','scope':'ALL V27 CURRENT HOME, TEN PAGES, RESONANCE, 14 WORLDS','source_zip_sha256':sha(MAIN.read_bytes()),'source_files_count':v27_count},
 'addons':{'pr':251,'source_head':'d4380adf1b3d8aa4f7659928bc551dd1fb27c86a','pc_v25_source_sha256':sha(PC25.read_bytes()),'pc_v25_web_resources':len(pc25),'v24_missing_resource_source_sha256':sha(PC24.read_bytes()),'v24_only_fallback':sorted(missing),'onepass_source_sha256':sha(ONEPASS.read_bytes()),'original_genesis_contract':'nox-genesis-live-evidence-v1','genesis_host_gate':'HOLD_UNLESS_ONEHOST_INJECTS_TRUSTED_SAME_ORIGIN_META'},
 'immutable':{'home_index_sha256':sha(site['index.html']),'original_d02_sha256':sha(site['nox-home.mjs']),'14_pbr_worlds_sha256':sha(site['nox-engines/physical-worlds-v7.mjs']),'owner_approved_art_sha256':sha(site['assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp']),'root_nox_chat_sha256':sha(site['nox-chat.js']),'root_catalog_sha256':sha(site['nox-function-catalog.js'])},
 'mutation_policy':{'v27_existing_files_modified':mutations[:3],'pc_files_modified':mutations[3:],'pc_v25_normalizations':normalized,'pc_vendor_key_sanitization':security_sanitized,'v27_other_files_byte_identical':True,'no_second_active_home':True,'v25_pc_original_home_preserved_as_reference':True},
 'test_claims':{'v27_chromium_baseline':'PR241 GitHub 43309342605 7/7 viewports 10/10 pages 10/10 V26 clicks V27 favorites/recents','new_merged_hardware_windows_gpu':'NOT_TESTED','new_merged_live_onehost_s03_stop':'HOLD','production_changed':False,'release_accepted':False},
 'site_files_before_receipts':len(site),
 'archive_fingerprint_manifest_sha256':None,
 'old_intermediate_archives_deleted_from_user_drive':False,
 'note':'Do not delete historical original PC/V27 ZIPs until Windows OneHost independent same-SHA acceptance. Only current V27 is primary. No new backend or AI model.'
}
manifest={p:{'sha256':sha(b),'bytes':len(b)} for p,b in sorted(site.items())}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
receipt['archive_fingerprint_manifest_sha256']=sha(manifest_bytes)
site['SOURCE_MANIFEST_V28.json']=manifest_bytes
site['NOX_V28_UNIFIED_RECEIPT.json']=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode()
readme='''NOX HELION UNIFIED V28 — 13.11.2026

PRIMARY = physically verified NOX WEB V27 (PR #241, exact SHA 64053cead613ab646f7dcf05ea68479bab8bf434).
No replacement of original HOME D02, 8 CoreID, original 14 PBR worlds or V27 Resonance.
ADDONS = PC CHAT V25 (PR #251) in site/pc/, 7 missing assets from PC V24,
OnePass V2 original QA read-only, physical GENESIS/S03 evidence panel adapted from PR #251.
Only V27 chat.html, memory.html, training.html are augmented by import of a compact
secondary module. PC chat and memory are reachable as secondary buttons from
those original V27 pages. PC index.html redirects to ../index.html;
the original PC index is kept under reference/ as non-active rollback evidence.
V27 original root chat, function catalog, WebGL and original HOME are byte-identical.
GENESIS does NOT invent API: it shows HOLD until existing authorized OneHost
injects a same-origin <meta name="nox-genesis-evidence-endpoint" content="/verified/path">.
No extra service, no data upload, no training START or local model downloads.
The addon panel is a small secondary toolbar; main HOME is untouched.
READ: NOX_V28_UNIFIED_RECEIPT.json + SOURCE_MANIFEST_V28.json.
QA under qa/v27_browser/ is PREVIOUS V27 evidence, not new Windows QA.
RELEASE: SOURCE CANDIDATE. Windows OneHost/S03/STOP/GPU independent acceptance HOLD.
Rollback: original archives are preserved and sources are namespaced.
'''
site['READ_ME_FIRST_V28.txt']=readme.encode('utf8')
# Internal zip (site/) plus proof files (top-level). Zip member order deterministic.
OUT.unlink(missing_ok=True)
start=time.time()
with zipfile.ZipFile(OUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as zout:
    for n,b in sorted(site.items()):
        zout.writestr('site/'+n,b)
with zipfile.ZipFile(OUT) as z:
    bad=z.testzip()
    assert bad is None,('OUTPUT_CRC_FAIL',bad)
    assert len(z.namelist())==len(site)
    for n in main:
        if n not in ['chat.html','memory.html','training.html']:
            assert sha(z.read('site/'+n))==sha(main[n]),'NO_LOSS:'+n
    assert sha(z.read('site/index.html'))==HASH['index']
    assert sha(z.read('site/nox-home.mjs'))==HASH['d02']
    assert sha(z.read('site/nox-engines/physical-worlds-v7.mjs'))==HASH['pbr']
    assert sha(z.read('site/assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp'))==HASH['approved_home']
    assert all(('site/pc/'+n) in z.namelist() for n in pc25)
    assert all(('site/pc/'+n) in z.namelist() for n in missing)
    assert all(z.read('site/'+n).count(b'nox-v28-pc-genesis-addons.mjs')==1 for n in ['chat.html','memory.html','training.html'])
receipt['final_archive']={'bytes':OUT.stat().st_size,'sha256':sha(OUT.read_bytes()),'members':len(site),'build_seconds':round(time.time()-start,2),'zip_crc':'PASS','all_original_v27_unchanged_except_3_secondary_html':True}
EVIDENCE.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'archive':str(OUT),'members':len(site),'bytes':OUT.stat().st_size,'sha256':receipt['final_archive']['sha256'],'crc':'PASS','v27_original_files':v27_count,'pc25_addons':len(pc25),'pc24_missing':len(missing),'original_qa':countqa,'v27_browser_evidence':len(prior_qa),'changed_v27_pages':3,'normalized_pc_paths':len(normalized),'sensitive_vendor_keys_sanitized':security_sanitized,'elapsed':receipt['final_archive']['build_seconds']},ensure_ascii=False))