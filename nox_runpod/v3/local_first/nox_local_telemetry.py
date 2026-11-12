#!/usr/bin/env python3
"""Publish read-only LOCAL trainer facts for later authenticated OneHost ingestion.

No HTTP server, no GPU commands, no re-starts and no model writes. Source receipts must be local.
"""
from __future__ import annotations
import argparse,datetime,json,os,sys
from nox_local_preflight import local_path


def inspect(preflight:dict,train:dict|None=None,mtime_age:int|None=None):
    result={
      'schema':'nox-training-local-telemetry-v1',
      'source':'LOCAL_CONTAINER_READ_ONLY',
      'modelFamily':'Qwen3.6-35B-A3B SFT/PEFT (archived trainer)',
      'fullStudentWeightsVerified':False,
      'teacherFusionVerified':False,'windowsSyncVerified':False,
      'intelligenceProgressPercent':None,
      'checkpointStep':None,'checkpointBackupHashMatched':False,
      'liveStep':None,'liveTarget':None,'stepCompletionPercent':None,
      'status':'HOLD','reason':'LOCAL_DATA_NOT_VERIFIED'}
    if preflight.get('schema')!='nox-local-io-audit-v1':return result
    if preflight.get('status')=='HOLD':
      result['reason']='PREFLIGHT_HOLD'
      return result
    result['checkpointStep']=preflight.get('observedStep') if isinstance(preflight.get('observedStep'),int) else None
    result['checkpointBackupHashMatched']=preflight.get('externalBackupDigestMatched') is True
    if not result['checkpointBackupHashMatched']:
      result['reason']='JAPANESE_BACKUP_DIGEST_NOT_CONFIRMED'
      return result
    result['status']='LOCAL_CHECKPOINT_HASH_MATCHED'
    result['reason']='STUDENT_FULL_WEIGHTS_AND_WINDOWS_STILL_HOLD'
    if not isinstance(train,dict) or mtime_age is None or mtime_age>120 or mtime_age<0:
      return result
    step,total=train.get('step'),train.get('total')
    if not isinstance(step,int) or isinstance(step,bool) or not isinstance(total,int) or isinstance(total,bool) or total<1 or step<0 or step>total:
      return result
    result['liveStep']=step;result['liveTarget']=total
    result['stepCompletionPercent']=round(100*step/total,2)
    # A fresh JSON status only proves file update, not GPU execution or identity.
    result['status']='LOCAL_TRAINER_STATUS_FILE_FRESH'
    result['reason']='LIVE_PID_AND_GPU_STEPS_NOT_INDEPENDENTLY_VERIFIED'
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preflight',required=True)
    p.add_argument('--trainer-status',help='Optional LOCAL status_sft.json from the original training script')
    p.add_argument('--output',help='Optional LOCAL atomic JSON output for existing owner sync')
    a=p.parse_args(argv)
    try:
      with open(local_path(a.preflight),encoding='utf8') as f: pre=json.load(f)
      train=None;age=None
      if a.trainer_status:
        src=local_path(a.trainer_status)
        if os.path.isfile(src):
          with open(src,encoding='utf8') as f:train=json.load(f)
          age=int(datetime.datetime.now(datetime.timezone.utc).timestamp()-os.stat(src).st_mtime)
      state=inspect(pre,train,age)
      state['generatedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
      if a.output:
        dest=local_path(a.output)
        os.makedirs(os.path.dirname(dest),exist_ok=True)
        tmp=dest+'.nox-tmp-'+str(os.getpid())
        with open(tmp,'x',encoding='utf8') as f:json.dump(state,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
      print(json.dumps(state,ensure_ascii=False,indent=2))
      return 0 if state['status']!='HOLD' else 2
    except (OSError,ValueError,json.JSONDecodeError) as e:
      print(json.dumps({'schema':'nox-training-local-telemetry-v1','status':'HOLD','error':str(e)[:170]}));return 2

if __name__=='__main__':sys.exit(main())
