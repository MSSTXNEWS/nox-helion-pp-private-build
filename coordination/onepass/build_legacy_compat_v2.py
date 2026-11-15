"""Append minimal native-owner-only legacy chat compatibility to REAL verified V29.3.

Input is byte-pinned V29.3 ONEPASS archive. Output preserves original archived
files, adds one owner-gated JS module, and adjusts one legacy SSE consumer
ONLY when on native-owner stage; Windows legacy mode remains unchanged.
"""
from __future__ import annotations
import argparse,hashlib,json,os,posixpath,zipfile
from pathlib import Path

BASE_SHA='e70f0439fdf0a028c1d52fc638a38086aa7863fb7b33733a9609532dd544a9d5'
BASE_COUNT=1090
NATIVE_SCRIPT='site/nox-legacy-chat-bridge-v293.js'
SSE_CLIENT='site/pc/pages/_kit/nox-pages.js'
KIT_SHA='09fbb1989e767f63d4910751d5c0c038ec9039d7b385a7e449e09e27d94b4d32'
PAGES=['site/index.html','site/cinema.html','site/pc/home-v18.html','site/pc/cinema.html']+[
    f'site/pc/pages/{name}/index.html'
    for name in ('canvas','cinema','code','games','graph','image','music','observatory','reader','voice')]

def digest(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def sha_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for buf in iter(lambda:f.read(1024*1024),b''):h.update(buf)
    return h.hexdigest()

def patch_legacy_client(raw:bytes)->bytes:
    if digest(raw)!=KIT_SHA:raise ValueError('HOLD_ORIGINAL_SSE_CLIENT_SOURCE_SHA')
    text=raw.decode('utf-8')
    old="const rd=r.body.getReader(),dec=new TextDecoder();let buf='',out='',err=null;"
    new="const rd=r.body.getReader(),dec=new TextDecoder();let buf='',out='',err=null,doneVerified=false;"
    if text.count(old)!=1:raise ValueError('HOLD_SSE_CLIENT_ANCHOR_1')
    text=text.replace(old,new,1)
    old="if(ev.type==='done'&&!out&&ev.note)err=ev.note;"
    new="""if(ev.type==='done'){
        if(ev.saved===true&&ev.s03_integrated===true&&ev.history_persisted===true&&
           typeof ev.exchange_id==='string'&&ev.exchange_id.length>=6)doneVerified=true;
        else if(!out&&ev.note)err=ev.note;
      }"""
    if text.count(old)!=1:raise ValueError('HOLD_SSE_CLIENT_ANCHOR_2')
    text=text.replace(old,new,1)
    old="if(err&&!out)throw new Error(err);return out};"
    new="""const ownerStage=window.NOX_NATIVE_OWNER===true&&location.pathname.startsWith('/nox-web-v29/');
  if(err&&(ownerStage||!out))throw new Error(err);
  if(ownerStage&&!doneVerified)throw new Error('HOLD_NATIVE_DONE_NOT_VERIFIED');
  return out};"""
    if text.count(old)!=1:raise ValueError('HOLD_SSE_CLIENT_ANCHOR_3')
    text=text.replace(old,new,1)
    return text.encode('utf-8')

def patch_html(data:bytes,name:str)->bytes:
    text=data.decode('utf-8')
    if text.count('</head>')!=1:raise ValueError('HOLD_PAGE_HEAD_ANCHOR_'+name)
    sub=posixpath.relpath(NATIVE_SCRIPT[5:],posixpath.dirname(name[5:]) or '.')
    html=f'<script src="{sub}" defer></script>'
    if html in text or 'nox-legacy-chat-bridge-v293.js' in text:
        raise ValueError('HOLD_DUPLICATE_SCRIPT_'+name)
    return text.replace('</head>',html+'\n</head>',1).encode('utf-8')

def build(base:Path,out:Path,script:Path)->dict:
    if sha_file(base)!=BASE_SHA:raise ValueError('HOLD_BASE_SHA')
    if base.resolve()==out.resolve() or out.exists():raise ValueError('HOLD_OVERWRITE_OR_EXISTING_OUTPUT')
    js=script.read_bytes()
    if not 5000<len(js)<15000:raise ValueError('HOLD_SCRIPT_SIZE')
    content=js.decode('utf-8')
    for marker in ("window.NOX_NATIVE_OWNER === true", "/api/nox/chat/stream", "s03_integrated===true",
                   "HOLD_S03_COMMIT_RECEIPT", "HOLD_DIALOG_HISTORY_READBACK", "history_persisted:true"):
        if marker not in content:raise ValueError('HOLD_SCRIPT_CONTRACT_'+marker)
    pending=out.with_suffix(out.suffix+'.pending')
    if pending.exists():raise ValueError('HOLD_PENDING_EXISTS')
    changed={}
    try:
        with zipfile.ZipFile(base) as a,zipfile.ZipFile(pending,'w') as b:
            if len(a.namelist())!=BASE_COUNT or a.testzip() is not None:raise ValueError('HOLD_BASE_INTEGRITY')
            if NATIVE_SCRIPT in a.namelist():raise ValueError('HOLD_SCRIPT_PRESENT')
            if not set(PAGES+[SSE_CLIENT]).issubset(a.namelist()):raise ValueError('HOLD_MISSING_ORIGINAL_FILES')
            for info in a.infolist():
                blob=a.read(info)
                updated=patch_html(blob,info.filename) if info.filename in PAGES else (patch_legacy_client(blob) if info.filename==SSE_CLIENT else blob)
                if updated!=blob:changed[info.filename]={'before':digest(blob),'after':digest(updated)}
                b.writestr(info,updated)
            b.writestr(NATIVE_SCRIPT,js,compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(pending) as z:
            if len(z.namelist())!=BASE_COUNT+1 or z.testzip()!=None:raise ValueError('HOLD_DERIVED_ZIP_CRC')
            if digest(z.read(NATIVE_SCRIPT))!=digest(js):raise ValueError('HOLD_SCRIPT_HASH')
            if len(changed)!=len(PAGES)+1:raise ValueError('HOLD_UNEXPECTED_CHANGED_FILES')
        os.replace(pending,out)
    except Exception:
        pending.unlink(missing_ok=True)
        raise
    return {'schema':'NOX_V293_ONEPASS_NATIVE_OWNER_LEGACY_PROTOCOL_COMPAT_V2',
        'base_zip_sha256':BASE_SHA,'base_entries':BASE_COUNT,
        'derived_zip_sha256':sha_file(out),'derived_entries':BASE_COUNT+1,
        'base_entries_unchanged':BASE_COUNT-len(changed),'html_pages_injected':len(PAGES),
        'native_sse_client_guarded':1,'new_js_modules':1,
        'js_sha256':digest(js),'changes':changed,
        'native_model_live_e2e':'HOLD_PROVIDER_ACCESS',
        'local_chromium_fixture_tests':'SEPARATE_TEST_RECEIPT',
        'windows_mode_modified':False,'new_backend':False,'original_weights_or_s03_mutated':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--script',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args();r=build(a.base,a.output,a.script);a.receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in r.items() if k!='changes'},ensure_ascii=False,indent=2))
