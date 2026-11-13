"""NOX V37 protected model and curriculum registry. No trainer starts from filename alone."""
from __future__ import annotations
import hashlib,json,re


def _hex64(s):return isinstance(s,str) and re.fullmatch(r'[0-9a-f]{64}',s) is not None

def check_job(model,job,receipt_db):
    """Only SHA+dataset+objective+optimizer receipt can certify previous work."""
    if not isinstance(job,dict) or not isinstance(model,dict):return {'state':'HOLD_SCHEMA'}
    if not _hex64(model.get('sha256')) or not _hex64(job.get('dataset_sha256')):
        return {'state':'HOLD_SHA_REQUIRED'}
    if not job.get('objective') or job.get('kind') not in ('teacher_answers','student_sft','distillation','eval','graphics','video'):
        return {'state':'HOLD_JOB_TYPE'}
    key=hashlib.sha256(json.dumps({'model':model['sha256'],'data':job['dataset_sha256'],
                                  'objective':job['objective'],'kind':job['kind']},sort_keys=True).encode()).hexdigest()
    for rec in receipt_db:
        if rec.get('job_fingerprint')==key and rec.get('native_verified') is True:
            if rec.get('status')=='COMPLETED_WITH_SHA_AND_EVAL':
                return {'state':'SKIP_ALREADY_VERIFIED','fingerprint':key,'checkpoint':rec.get('checkpoint_sha256')}
            if rec.get('status')=='RUNNING':
                return {'state':'PROTECT_RUNNING_NO_DUPLICATE','fingerprint':key}
    return {'state':'NEW_JOB_REQUIRES_NATIVE_OWNER_GRANT','fingerprint':key}
