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
            return exc.code,None
        except (OSError,ValueError):
            return 0,None
    return 0,None
def unpack(payload):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        for key in ('instances','results','data'):
            value=payload.get(key)
            if isinstance(value,list):return value
            if isinstance(value,dict) and isinstance(value.get('instances'),list):
                return value['instances']
    return None
def main():
    key=os.environ.get('NOX2','')
    if not key:
        print('NOX_V131_HOLD=NOX2_MISSING')
        return 2
    outcomes=[]
    urls=(
      ('V1_CONSOLE_LIST','https://console.vast.ai/api/v1/instances/?limit=25'),
      ('V1_CLOUD_LIST','https://cloud.vast.ai/api/v1/instances/?limit=25'),
      ('V0_CONSOLE_DETAIL','https://console.vast.ai/api/v0/instances/'+str(INSTANCE)+'/'),
      ('V0_CLOUD_DETAIL','https://cloud.vast.ai/api/v0/instances/'+str(INSTANCE)+'/'))
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
    return 0 if any(x['http']==200 for x in outcomes) else 2
if __name__=='__main__':raise SystemExit(main())
