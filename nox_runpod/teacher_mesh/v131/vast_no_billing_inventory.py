"""V131: read-only Vast NOX2 connection inventory, no SSH, instance creation or secrets."""
from __future__ import annotations
import json,os,time,urllib.error,urllib.request

API="https://console.vast.ai/api/v0"
INSTANCE=60509551
def get(path,key):
    req=urllib.request.Request(API+path,headers={
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
    for path in ('/instances/','/instances/'+str(INSTANCE)+'/','/instances/'+str(INSTANCE)):
        code,value=get(path,key)
        records=unpack(value)
        direct_id=value.get('id') if isinstance(value,dict) else None
        target=next((v for v in records if isinstance(v,dict) and str(v.get('id'))==str(INSTANCE)),None) if records else None
        outcomes.append({'endpoint_kind':'LIST' if path=='/instances/' else 'DETAIL_SLASH' if path.endswith('/') else 'DETAIL_NO_SLASH',
          'http':code,'list_count':len(records) if records is not None else None,
          'target_present':bool(target or str(direct_id)==str(INSTANCE)),
          'target_status':str((target or value if direct_id is not None else target or {}).get('actual_status','UNKNOWN'))[:30]
          if isinstance(target or value if direct_id is not None else target,dict) else 'UNKNOWN'})
    print('NOX_V131_VAST_READ_ONLY='+json.dumps({'instance':INSTANCE,'checks':outcomes,
        'ssh_key_created':False,'server_modified':False,'no_new_billing':True},separators=(',',':')))
    print('NOX_V131_READONLY_COMPLETE=true')
    return 0 if any(x['http']==200 for x in outcomes) else 2
if __name__=='__main__':raise SystemExit(main())
