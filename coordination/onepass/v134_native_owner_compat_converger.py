"""NOX V134: combine V133 full WEB with verified original OneHost native chat.

One immutable source, one owner-only native chat adapter, no second backend.
Not a production installer. Keep original frozen owner nox-ui.js on disk:
the EXISTING OneHost V122 StaticFiles overlays it at read-time after verifying
the original SHA. Storing the overlaid JS in site/ would yield HTTP 409.
All stage changes have immediate previous bytes in rollback/v134-stage/.
"""
from __future__ import annotations
import argparse, hashlib, json, os, zipfile
from pathlib import Path
from .build_legacy_compat_v2 import (
    NATIVE_SCRIPT, SSE_CLIENT, KIT_SHA, PAGES, patch_legacy_client, patch_html
)

BASE_SHA='2ac6be7b5f84e77f35f9b8b1dbfb25cab72e197f0d9f0aad70b886166a296bc4'
FROZEN_SHA='166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0'
BRIDGE_JS_SHA='f953f83cb49087847b7125ff85a8cbf791ecc9de2f9efb44b7140e548b5f2c4d'
OWNER_FROZEN_SHA='c5f6b23d5fc6c31c4c388a574bfa8c61243cda6000cefb0026732ebe4183b765'
OWNER_V122_SHA='18d8c8d6009323188b9f903920308b3b871a6123f7b425a77184a6b2c147640e'
FROZEN_N=1089
V133_N=1106
OWNER='site/nox-ui.js'
MANIFEST='NOX_V134_NATIVE_OWNER_COMPAT_MANIFEST.json'
README='NOX_V134_INTEGRATION_README_RU.md'
ORIGINAL_V133_MANIFEST='NOX_V133_CONVERGED_1090_WEB_ASSET_MANIFEST.json'
PREVIOUS='rollback/v134-stage/'
CURRENT_HTML=set(PAGES)
STAGE_CHANGES=CURRENT_HTML|{SSE_CLIENT,OWNER}
FINAL_CHANGED_FROZEN=18 # 9 V133 - 1 V122 owner + 15 new native chat - 5 overlap
NEW_SITE_ASSETS=2 # existing PR281 graphics buttons plus native legacy chat adapter

def digest(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def file_sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def _member(name,raw):
    if name.startswith('/') or '..' in Path(name).parts or '\\' in name:
        raise ValueError('HOLD_V134_MEMBER_TRAVERSAL')
    info=zipfile.ZipInfo(name,date_time=(2026,11,15,0,0,0))
    info.external_attr=0o100644<<16
    info.compress_type=zipfile.ZIP_DEFLATED
    return info,raw

def build(stage:Path,frozen:Path,js:Path,output:Path)->dict:
    stage,frozen,js,output=map(Path,(stage,frozen,js,output))
    if not stage.is_file() or file_sha(stage)!=BASE_SHA:
        raise ValueError('HOLD_V133_CONVERGED_SOURCE_SHA')
    if not frozen.is_file() or file_sha(frozen)!=FROZEN_SHA:
        raise ValueError('HOLD_ORIGINAL_V29_FROZEN_SOURCE_SHA')
    if not js.is_file() or digest(js.read_bytes())!=BRIDGE_JS_SHA:
        raise ValueError('HOLD_NATIVE_COMPAT_JS_SHA')
    if output.exists() or output.resolve() in (stage.resolve(),frozen.resolve()):
        raise ValueError('HOLD_SOURCE_OVERWRITE')
    temp=output.with_name(output.name+'.nox-v134-pending')
    if temp.exists():raise ValueError('HOLD_PENDING_OUTPUT_EXISTS')
    previous={};newdata={};modified=[]
    try:
        with zipfile.ZipFile(stage) as a,zipfile.ZipFile(frozen) as f:
            if a.testzip() is not None or f.testzip() is not None:
                raise ValueError('HOLD_SOURCE_ZIP_CRC')
            stage_paths=a.namelist()
            frozen_paths=f.namelist()
            if (len(stage_paths)!=V133_N or len(frozen_paths)!=FROZEN_N or
                len(set(stage_paths))!=V133_N or len(set(frozen_paths))!=FROZEN_N):
                raise ValueError('HOLD_SOURCE_FILE_COUNT')
            if not set(frozen_paths).issubset(stage_paths):
                raise ValueError('HOLD_FROZEN_MEMBER_LOSS')
            if not STAGE_CHANGES.issubset(stage_paths) or NATIVE_SCRIPT in stage_paths:
                raise ValueError('HOLD_COMPAT_ORIGINAL_ANCHORS')
            v133_meta=json.loads(a.read(ORIGINAL_V133_MANIFEST))
            if (v133_meta.get('frozen_sha256')!=FROZEN_SHA or
                v133_meta.get('original_paths_preserved')!=FROZEN_N):
                raise ValueError('HOLD_V133_PROVENANCE')
            orig_owner=f.read(OWNER)
            stage_owner=a.read(OWNER)
            if digest(orig_owner)!=OWNER_FROZEN_SHA or digest(stage_owner)!=OWNER_V122_SHA:
                raise ValueError('HOLD_V122_STATIC_SOURCE_PIN')
            if digest(a.read(SSE_CLIENT))!=KIT_SHA:
                raise ValueError('HOLD_ORIGINAL_NATIVE_SSE_CLIENT_PIN')
            script=js.read_bytes()
            with zipfile.ZipFile(temp,'x',allowZip64=True) as dst:
                for info in a.infolist():
                    name=info.filename
                    raw=a.read(info)
                    if name in CURRENT_HTML:
                        changed=patch_html(raw,name)
                    elif name==SSE_CLIENT:
                        changed=patch_legacy_client(raw)
                    elif name==OWNER:
                        # Source pin must remain intact for existing OneHost
                        changed=orig_owner
                    else:changed=raw
                    if raw!=changed:
                        if name not in STAGE_CHANGES:raise ValueError('HOLD_UNEXPECTED_STAGE_CHANGE')
                        previous[name]=raw
                        modified.append({'name':name,'stage_sha256':digest(raw),
                                         'final_sha256':digest(changed)})
                    dst.writestr(info,changed)
                for name,raw in sorted(previous.items()):
                    dst.writestr(*_member(PREVIOUS+name,raw))
                dst.writestr(*_member(NATIVE_SCRIPT,script))
                readme=(
                    'NOX HELION V134 / ONEPASS OWNER NATIVE CHAT COMPAT / SOURCE ONLY\n'
                    'This is a derivative of V133 (1089 original paths retained).\n'
                    'Existing OneHost /nox-web-v29 serves ORIGINAL frozen site/nox-ui.js '
                    'and injects verified V122 HTTP response overlay; DO NOT replace with patched V122 file on disk.\n'
                    '14 original HTML pages load real owner-scoped legacy chat JS; '
                    'original /api/nox/chat legacy JSON/SSE is routed to existing '
                    '/api/nox/chat/stream with original S03 dialog commit and readback checks.\n'
                    'The actual original SSE client is receipt-gated only in native owner staging. '
                    'Windows original behavior is retained.\n'
                    'Original V133 archive remains immutable; any V134 change can be undone '
                    'using rollback/v134-stage/*. No second backend, DB, scheduler, weights.\n'
                    'Latest 23/92 registered OneHost API paths, native installation blocked '
                    'by invalid Vast NOX2 auth_error; owner Windows full E2E unverified.\n'
                )
                dst.writestr(*_member(README,readme.encode('utf8')))
                manifest={
                    'schema':'NOX_V134_NATIVE_OWNER_COMPAT_FULL_WEB_V293_V1',
                    'instructions_version':'0.0.6','stage_v133_sha256':BASE_SHA,
                    'frozen_web_sha256':FROZEN_SHA,
                    'existing_onehost_owner_v122_response_sha256':OWNER_V122_SHA,
                    'existing_onehost_owner_disk_source_sha256':OWNER_FROZEN_SHA,
                    'compat_js_sha256':BRIDGE_JS_SHA,
                    'original_paths_preserved':FROZEN_N,
                    'original_paths_changed':FINAL_CHANGED_FROZEN,
                    'original_paths_unchanged':FROZEN_N-FINAL_CHANGED_FROZEN,
                    'stage_paths_changed':len(modified),
                    'prior_stage_rollback_count':len(previous),
                    'new_site_modules':NEW_SITE_ASSETS,
                    'native_compat_html_pages':len(CURRENT_HTML),
                    'native_compat_sse_client_count':1,
                    'native_compat_real_route':'/api/nox/chat/stream',
                    'legacy_route':'/api/nox/chat',
                    'existing_s03_only':True,
                    'original_windows_legacy_protocol_unchanged':True,
                    'all_92_web_e2e_accepted':False,
                    'native_owner_deployed':False,
                    'full_weight_optimizer_accepted':False,
                    'windows_physical_accepted':False,
                    'modifications':sorted(modified,key=lambda x:x['name'])}
                dst.writestr(*_member(MANIFEST,
                    (json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()))
        proof=verify(temp,frozen=frozen)
        if output.exists():raise ValueError('HOLD_CONCURRENT_SOURCE_OUTPUT')
        os.link(temp,output)
        temp.unlink()
        proof['file']=output.name
        return proof
    finally:
        temp.unlink(missing_ok=True)

def verify(archive:Path,*,frozen:Path|None=None)->dict:
    archive=Path(archive)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('HOLD_V134_ZIP_CRC')
        names=z.namelist()
        if len(set(names))!=len(names):raise ValueError('HOLD_V134_DUPLICATE')
        manifest=json.loads(z.read(MANIFEST))
        if (manifest.get('schema')!='NOX_V134_NATIVE_OWNER_COMPAT_FULL_WEB_V293_V1'
            or manifest.get('stage_v133_sha256')!=BASE_SHA
            or manifest.get('prior_stage_rollback_count')!=16
            or manifest.get('original_paths_changed')!=FINAL_CHANGED_FROZEN
            or manifest.get('native_compat_html_pages')!=14):
            raise ValueError('HOLD_V134_MANIFEST')
        mods=manifest['modifications']
        if len(mods)!=16 or set(x['name'] for x in mods)!=STAGE_CHANGES:
            raise ValueError('HOLD_V134_CHANGE_SET')
        if digest(z.read(OWNER))!=OWNER_FROZEN_SHA:
            raise ValueError('HOLD_V134_ONEHOST_STATIC_OWNER_PIN')
        if digest(z.read(NATIVE_SCRIPT))!=BRIDGE_JS_SHA:
            raise ValueError('HOLD_V134_COMPAT_JS_PIN')
        for x in mods:
            p=x['name']
            if digest(z.read(p))!=x['final_sha256'] or digest(z.read(PREVIOUS+p))!=x['stage_sha256']:
                raise ValueError('HOLD_V134_ROLLBACK_SHA_'+p)
        expected=V133_N+len(mods)+3
        if len(names)!=expected:
            raise ValueError('HOLD_V134_OUTPUT_MEMBER_COUNT')
        if frozen is not None:
            with zipfile.ZipFile(frozen) as f:
                if f.testzip() is not None:raise ValueError('HOLD_V134_ORIGINAL_CRC')
                fs=f.namelist()
                if len(fs)!=FROZEN_N or not set(fs).issubset(names):
                    raise ValueError('HOLD_V134_FROZEN_MEMBER_LOSS')
                changed=sum(z.read(p)!=f.read(p) for p in fs)
                if changed!=FINAL_CHANGED_FROZEN:
                    raise ValueError('HOLD_V134_FROZEN_DIFF_COUNT')
        return {'state':'V134_FULL_WEB_SOURCE_SHA_CRC_PASS',
                'sha256':file_sha(archive),'bytes':archive.stat().st_size,
                'total_members':len(names),'original_paths_retained':FROZEN_N,
                'original_paths_unchanged':FROZEN_N-FINAL_CHANGED_FROZEN,
                'stage_rollback_verified':16,'owner_disk_original_pin_verified':True,
                'native_legacy_chat_adapter_source_integrated':True,
                'production_deployed':False,'full_92_e2e_accepted':False}

def main()->int:
    parser=argparse.ArgumentParser()
    for name in ('stage','frozen','compat-js','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    receipt=build(args.stage,args.frozen,getattr(args,'compat_js'),args.output)
    print('NOX_V134_FULL_CONVERGED_SOURCE='+json.dumps(receipt,sort_keys=True,separators=(',',':')))
    return 0

if __name__=='__main__':raise SystemExit(main())
