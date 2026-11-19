"""V131: read-only Vast NOX2 connection inventory, no SSH, instance creation or secrets."""
from __future__ import annotations
import json,os,time,urllib.error,urllib.request

INSTANCE=60509551
def get(url,key):
    req=urllib.request.Request(url,headers={
        'Authorization':'Bearer '+key,'Accept':'application/json'},method='GET')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=15) as response:
                data=response.read(1000000)
                return response.status,json.loads(data)
        except urllib.error.HTTPError as exc:
            if exc.code==429 and attempt<2:
                time.sleep((5,10)[attempt]);continue
            try:
                error = json.loads(exc.read(4096))
                reason = error.get('error') if isinstance(error, dict) else None
            except (ValueError, UnicodeError):
                reason = None
            return exc.code, {'error': reason} if reason in ('auth_error','invalid_token','not_found') else None
        except (OSError,ValueError):
            return 0,None
    return 0,None
def unpack(payload):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        for key in ('instances','results','data','items'):
            value=payload.get(key)
            if isinstance(value,list):return value
            if isinstance(value,dict) and isinstance(value.get('instances'),list):
                return value['instances']
    return None
def main():
    key=os.environ.get('NOX2','')
    if not key or key.startswith(('tid_', 'tsec_', 'github_pat_')):
        print('NOX_V131_HOLD=VAST_KEY_MISSING_OR_WRONG_PROVIDER')
        return 2
    outcomes=[]
    # Vast deprecated v0 account-wide listing in August 2026.
    # Query the owner-scoped documented v1 collection; never infer absence
    # from a deprecated 404 or an unbounded external account list.
    urls=(
      ('V1_CONSOLE_LIST','https://console.vast.ai/api/v1/instances/?owner=me'),
      ('V1_CLOUD_LIST','https://cloud.vast.ai/api/v1/instances/?owner=me'))
    for label,url in urls:
        code,value=get(url,key)
        records=unpack(value)
        direct=value.get('instances',value) if isinstance(value,dict) else None
        if isinstance(direct,list):direct=None
        target=next((v for v in records if isinstance(v,dict) and str(v.get('id'))==str(INSTANCE)),None) if records else None
        if isinstance(direct,dict) and str(direct.get('id'))==str(INSTANCE):target=direct
        error=value.get('error') if isinstance(value,dict) else None
        outcomes.append({'endpoint_kind':label,'http':code,
          'list_count':len(records) if records is not None else None,
          'target_present':isinstance(target,dict),
          'target_status':str(target.get('actual_status','UNKNOWN'))[:30] if isinstance(target,dict) else 'UNKNOWN',
          'provider_error':str(error)[:40] if isinstance(error,str) else None})
    print('NOX_V131_VAST_READ_ONLY='+json.dumps({'instance':INSTANCE,'checks':outcomes,
        'ssh_key_created':False,'server_modified':False,'no_new_billing':True},separators=(',',':')))
    print('NOX_V131_READONLY_COMPLETE=true')
    print('NOX_V131_NATIVE_SSH_AUTHENTICATED=false')
    print('NOX_V131_NATIVE_COMMAND_EXECUTED=false')
    # Access to any account-level API is insufficient: the exact existing
    # instance must belong to this account and be RUNNING before native writes.
    confirmed=any(x['http']==200 and x['target_present'] is True and
                  x['target_status']=='running' for x in outcomes)
    print('NOX_V131_EXACT_EXISTING_RUNNING_INSTANCE='+str(confirmed).lower())
    return 0 if confirmed else 2
if __name__=='__main__':raise SystemExit(main())
