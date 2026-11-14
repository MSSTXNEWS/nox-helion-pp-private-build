"""NOX V108 native prepare V47 base-trainer JSONL inputs from V105 safe corpus.

One existing Vast instance, CPU only, no GPU allocation, no S03/weights edits.
On-disk only: owner-only private, hash-verified source, separate train/holdout.
Never export private examples to GitHub logs or use external cloud services.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

original_api=ssh.api
def settle(method,path,key,data=None):
    r=original_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib, json, os, re, shutil, stat, time
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V108_DATA_SCHEMA=NOX_PRIVATE_V105_TO_V47_FULL_BASE_TRAIN_CORPUS_V1')
SRC=Path('/root/nox/forge/curated_owner_sft_v105')
DST=Path('/root/nox/forge/base_train_input_v108')
FLOOR=10_000_000_000
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
      '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
SAFETY=re.compile(r'(?i)(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\b(?:passport|secret|token|diagnosis|medical|password|address|bank|patient)\b|\b(?:паспорт|адрес|диагноз|медицинск|парол|банковск)\w*)')
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()
def emit(status,**fields):
    result={'schema':'NOX_PRIVATE_SFT_V108_TRAINER_INPUT_RECEIPT_V1',
            'state':status,'weights_changed':False,'optimizer_steps':0,
            'private_training_data_exported':False,'original_v105_unchanged':True,
            's03_changed':False,'new_model_or_scheduler':False,**fields}
    print('NATIVE_V108_DATA_RESULT='+json.dumps(result,sort_keys=True,separators=(',',':'))[:1100])
def stopped():return any(Path(p).exists() for p in STOP)
def health(port):
    try:
        import urllib.request
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
            return r.status==200
    except Exception:return False
def verify_compatible(target, source):
    if not target.is_dir() or target.is_symlink():return False
    try:
        m=json.loads((target/'manifest.json').read_text(encoding='utf-8'))
        if m.get('schema')!='NOX_V108_V47_BASE_INPUT_V1' or m.get('v105_source_sha256')!=source['source_sha256']:
            return False
        for section in ('train','holdout'):
            p=target/(section+'.jsonl')
            if not p.is_file() or p.is_symlink() or digest(p)!=m.get(section+'_sha256'):
                return False
        return True
    except (ValueError,OSError):return False
try:
    if stopped():raise RuntimeError('HOLD_STOP')
    if not health(8080) or not health(8081):
        raise RuntimeError('HOLD_MAIN_CHAT_HEALTH')
    if not SRC.is_dir() or SRC.is_symlink():
        raise RuntimeError('HOLD_V105_CURATED_SOURCE')
    ms=SRC/'manifest.json'
    if not ms.is_file() or ms.is_symlink() or ms.stat().st_size>250_000:
        raise RuntimeError('HOLD_V105_MANIFEST')
    original=json.loads(ms.read_text(encoding='utf-8'))
    if original.get('schema')!='NOX_FORGE_OWNER_SFT_V105' or original.get('license')!='internal-owner-templates':
        raise RuntimeError('HOLD_V105_RIGHTS_AND_SCHEMA')
    if original.get('contains_raw_owner_legal_or_medical_records') is not False or original.get('dataset_private_only') is not True:
        raise RuntimeError('HOLD_V105_PRIVACY')
    if not isinstance(original.get('source_sha256'),str) or len(original['source_sha256'])!=64:
        raise RuntimeError('HOLD_V105_SOURCE_SHA')
    if DST.exists():
        if not verify_compatible(DST,original):raise RuntimeError('HOLD_EXISTING_V108_DATA_CONFLICT')
        m=json.loads((DST/'manifest.json').read_text(encoding='utf-8'))
        emit('EXISTING_BASE_TRAIN_CORPUS_VERIFIED',
             train_rows=m['train_rows'],holdout_rows=m['holdout_rows'],
             train_sha256=m['train_sha256'],holdout_sha256=m['holdout_sha256'])
        raise SystemExit(0)
    if DST.parent.is_symlink() or shutil.disk_usage(DST.parent).free < FLOOR+250_000_000:
        raise RuntimeError('HOLD_NEW_WRITE_10GB_RESERVE')
    stage=DST.parent/('.v108_base_input_stage_'+str(os.getpid()))
    if stage.exists():raise RuntimeError('HOLD_STAGE_CONFLICT')
    stage.mkdir(mode=0o700)
    rows_seen={}
    prompts_seen={}
    file_sha={}
    further_private_filtered={}
    try:
        for group in ('train','holdout'):
            src=SRC/(group+'.jsonl')
            if not src.is_file() or src.is_symlink() or src.stat().st_size>35_000_000:
                raise RuntimeError('HOLD_V105_'+group.upper()+'_FILE')
            if digest(src)!=original.get(group+'.jsonl_sha256'):
                raise RuntimeError('HOLD_V105_'+group.upper()+'_SOURCE_HASH')
            dest=stage/(group+'.jsonl')
            n=0;inspected=0;private_skipped=0
            with src.open('r',encoding='utf8') as inp, dest.open('x',encoding='utf8') as out:
                os.chmod(dest,0o600)
                for line in inp:
                    inspected+=1
                    if len(line)>30000:raise RuntimeError('HOLD_V105_ROW_SIZE')
                    try:obj=json.loads(line)
                    except ValueError:raise RuntimeError('HOLD_V105_ROW_JSON')
                    msgs=obj.get('messages')
                    if (not isinstance(msgs,list) or len(msgs)!=2 or
                        [m.get('role') for m in msgs if isinstance(m,dict)]!=['user','assistant']):
                        raise RuntimeError('HOLD_V105_ROW_ROLES')
                    prompt,answer=msgs[0].get('content'),msgs[1].get('content')
                    uri=obj.get('source_provenance')
                    rowsha=obj.get('source_row_sha256')
                    if (not isinstance(prompt,str) or not isinstance(answer,str) or
                        not isinstance(uri,str) or not isinstance(rowsha,str) or
                        len(rowsha)!=64 or not re.fullmatch('[0-9a-f]{64}',rowsha) or
                        not prompt.strip() or not answer.strip() or
                        len(prompt)>5000 or len(answer)>9000 or
                        obj.get('source_license')!='internal-owner-templates'):
                        raise RuntimeError('HOLD_V105_RIGHTS_OR_ROW')
                    if SAFETY.search(prompt) or SAFETY.search(answer):
                        # Additional sensitive examples must not be copied
                        # into the new training set or logged.
                        private_skipped+=1
                        continue
                    fingerprint=hashlib.sha256(' '.join(prompt.casefold().split()).encode('utf8')).hexdigest()
                    if fingerprint in prompts_seen:
                        raise RuntimeError('HOLD_TRAIN_HOLDOUT_DUPLICATE_PROMPT')
                    prompts_seen[fingerprint]=group
                    if rowsha in rows_seen:
                        raise RuntimeError('HOLD_CROSS_CORPUS_SOURCE_DUPLICATE')
                    rows_seen[rowsha]=group
                    row={'prompt':prompt,'completion':answer,
                         'source_uri':'owner-template://sha256/'+rowsha,
                         'rights_verified':True,'privacy_approved':True,
                         'rights_basis':'internal-owner-templates',
                         'privacy_basis':'V105_private_filtered_owner_templates',
                         'external_publication_allowed':False}
                    out.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+'\n')
                    n+=1
                out.flush();os.fsync(out.fileno())
            expected=original.get(group+'_rows')
            if type(expected) is not int or inspected!=expected or n<30:
                raise RuntimeError('HOLD_V105_ROW_COUNT_OR_EXCLUSIONS')
            rows_seen[group]=n
            further_private_filtered[group]=private_skipped
            file_sha[group]=digest(dest)
        if stopped() or not health(8080) or not health(8081):
            raise RuntimeError('HOLD_CHAT_OR_STOP_AFTER_CONVERSION')
        manifest={'schema':'NOX_V108_V47_BASE_INPUT_V1',
                  'v105_source_sha256':original['source_sha256'],
                  'v105_train_sha256':original['train.jsonl_sha256'],
                  'v105_holdout_sha256':original['holdout.jsonl_sha256'],
                  'train_sha256':file_sha['train'],
                  'holdout_sha256':file_sha['holdout'],
                  'train_rows':rows_seen['train'],
                  'holdout_rows':rows_seen['holdout'],
                  'prompt_source_overlap':False,
                  'source_rights':'internal-owner-templates',
                  'privacy':'owner_private_filtered',
                  'further_private_rows_excluded':further_private_filtered,
                  'actual_training_started':False,
                  'native_onehost_lease_verified':False,
                  'checkpoint_restored':False}
        out=stage/'manifest.json'
        with out.open('x',encoding='utf8') as file:
            os.chmod(out,0o600)
            json.dump(manifest,file,sort_keys=True,indent=2)
            file.write('\n');file.flush();os.fsync(file.fileno())
        if stopped():raise RuntimeError('HOLD_STOP_BEFORE_PUBLISH')
        os.rename(stage,DST)
        if not verify_compatible(DST,original):
            raise RuntimeError('HOLD_POST_PUBLISH_READBACK')
        emit('V47_BASE_WEIGHT_TRAIN_DATA_READY',
             train_rows=rows_seen['train'],holdout_rows=rows_seen['holdout'],
             train_sha256=file_sha['train'],holdout_sha256=file_sha['holdout'],
             source_leakage_checked=True,rights_filtered=True,
             further_private_rows_excluded=further_private_filtered,
             disk_free_after=shutil.disk_usage(DST.parent).free)
    finally:
        if stage.exists():
            # Never delete an unverified partially prepared corpus.
            print('NATIVE_V108_PARTIAL_STAGE_RETAINED_FOR_REVIEW=true')
except Exception as e:
    reason=str(e)
    emit(reason if reason.startswith('HOLD_') and len(reason)<98 else 'HOLD_DATA_CONVERSION')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    ssh.REMOTE=REMOTE
    ssh.api=settle
    output=io.StringIO()
    okay=False
    try:
        with contextlib.redirect_stdout(output):okay=ssh.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V108_DATA_HOLD='+msg if msg.startswith('HOLD_') and len(msg)<100 else 'HOLD_NATIVE')
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if not ssh.cleanup():okay=False
        except Exception:
            okay=False
    rows=[]
    for line in output.getvalue().splitlines():
        if line.startswith(('NATIVE_V108_DATA_','TEMP_SSH_CLEANUP=')) and len(line)<1200:
            print(line)
            rows.append(line)
    passed=okay and any('"state":"V47_BASE_WEIGHT_TRAIN_DATA_READY"' in x or '"state":"EXISTING_BASE_TRAIN_CORPUS_VERIFIED"' in x for x in rows)
    print('NOX_V108_V47_CORPUS_READY='+str(bool(passed)).lower())
    return 0 if passed else 2
if __name__=="__main__":
    raise SystemExit(main())
