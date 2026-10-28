"""Optional self-contained staged Persona motion media, local ZIP only.

A source-approved still may be cinematically animated (camera motion) without
modifying the immutable approved face. The EV identity conflict remains non-active.
No network, no second media host, no P02-P05 mutations.
"""
from pathlib import Path
from zipfile import ZipFile
import json,hashlib,os,shutil,sys

ACTIVE=('KV','AM','LA','KW')
BLOCKED=('EV',)
PINNED_BUNDLE_SHA256='9abc124ce1a543417afcd2a08097c5d72b5901a10830869cf495fa7045330ec7'

def sha(data):return hashlib.sha256(data).hexdigest()
def stage(stage_root:Path,bundle:Path):
    stage_root=stage_root.resolve(strict=True);bundle=bundle.resolve(strict=True)
    if bundle.suffix.lower()!='.zip':raise ValueError('PERSONA_MEDIA_ZIP_ONLY')
    if sha(bundle.read_bytes())!=PINNED_BUNDLE_SHA256:raise ValueError('PERSONA_BUNDLE_SHA_HOLD')
    if not (stage_root/'NOX.P01.Shell.csproj').is_file():raise ValueError('ORIGINAL_ONEHOST_REQUIRED')
    dest=stage_root/'Assets/creative/personas'
    if dest.exists():raise ValueError('PERSONA_ASSETS_ALREADY_PRESENT_NO_OVERWRITE')
    with ZipFile(bundle) as z:
        names=z.namelist()
        if names.count('PERSONA_MOTION_MANIFEST.json')!=1 or len(names)!=len(set(names)):
            raise ValueError('PERSONA_BUNDLE_MANIFEST_DRIFT')
        m=json.loads(z.read('PERSONA_MOTION_MANIFEST.json').decode('utf-8'))
        if m.get('schema')!='NOX_PERSONA_PARALLAX_SILENT_LOOP_V1':raise ValueError('PERSONA_BUNDLE_SCHEMA')
        entries={x['id']:x for x in m['entries']}
        if set(entries)!=set(ACTIVE)|set(BLOCKED):raise ValueError('PERSONA_COUNT_REQUIRED')
        for name in BLOCKED:
            if entries[name]['approved_for_active_persona'] is not False:
                raise ValueError('UNAPPROVED_PERSONA_ACTIVATION_FORBIDDEN')
        plans=[]
        for name in ACTIVE:
            row=entries[name]
            if not row['approved_for_active_persona'] or row['status']=='IDENTITY_CONFLICT_HOLD':
                raise ValueError('PERSONA_OWNER_APPROVAL_REQUIRED')
            for field,checksum in [('loop_filename','loop_sha256'),('poster_filename','poster_sha256')]:
                fname=row[field]
                if fname!=Path(fname).name or fname not in names:raise ValueError('PERSONA_TRAVERSAL_OR_MISSING')
                if not fname.startswith('NOX_PERSONA_'+name+'_'):raise ValueError('PERSONA_ID_COLLISION')
                data=z.read(fname)
                if sha(data)!=row[checksum] or not data:raise ValueError('PERSONA_SHA_HOLD')
                plans.append((fname,data))
        # No writes until entire source verified (including all four source SHA pins).
        dest.mkdir(parents=True,exist_ok=False)
        try:
            for fname,data in plans:
                p=dest/fname;p.write_bytes(data)
                if sha(p.read_bytes())!=sha(data):raise ValueError('PERSONA_COPY_READBACK')
        except BaseException:
            shutil.rmtree(dest,ignore_errors=True)
            raise
    receipt={'schema':'NOX_PERSONA_STAGED_R15','active_count':len(ACTIVE),'identity_candidate_hold':len(BLOCKED),
             'source_bundle_sha256':sha(bundle.read_bytes()),'media_files':len(plans),
             'files':{name:sha(data) for name,data in plans},
             'camera_motion_real':True,'facial_animation':False,'lip_sync':False,
             'native_windows_accepted':False}
    (stage_root.parent/'PERSONA_STAGE_RECEIPT.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return receipt

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('usage: stage_persona_media.py STAGED_R11 PERSONA_MEDIA_ZIP')
    print(json.dumps(stage(Path(sys.argv[1]),Path(sys.argv[2])),ensure_ascii=False))