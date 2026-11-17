"""Runner-only read of existing Vast CloudCopy metadata; no credentials in output."""
import json, urllib.error, urllib.request, urllib.parse
URL='https://console.vast.ai/api/v0/users/cloud_integrations/'
OFFICIAL_SOURCE='https://docs.vast.ai/api-reference/accounts/show-connections'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def summarize(data):
    if not isinstance(data,list) or len(data)>1000:
        return {'state':'HOLD_CLOUDCOPY_RESPONSE_SCHEMA','connections_count':None,'destination_access_verified':False}
    counts={};valid=0
    for row in data:
        if not isinstance(row,dict) or type(row.get('id')) is not int or row['id']<0:continue
        valid+=1
        kind=str(row.get('cloud_type','')).lower()
        kind=kind if kind in {'drive','gdrive','s3','dropbox','b2','r2','azure','gcs','huggingface'} else 'other'
        counts[kind]=counts.get(kind,0)+1
    return {'state':'EXISTING_CLOUDCOPY_CONNECTIONS' if valid else 'NO_EXISTING_CLOUDCOPY_CONNECTIONS',
            'connections_count':valid,'provider_counts':counts,'destination_access_verified':False,
            'connection_ids_and_names_exported':False,'provider_mutations':0}
def allowed(url):
    p=urllib.parse.urlsplit(url)
    return (p.scheme=='https' and p.netloc=='console.vast.ai' and not p.query and not p.fragment
            and p.path in ('/api/v0/users/cloud_integrations','/api/v0/users/cloud_integrations/'))
def probe(key):
    try:
        url=URL;opener=urllib.request.build_opener(NoRedirect())
        for attempt in range(2):
            if not allowed(url):return {'state':'HOLD_CLOUDCOPY_REDIRECT_SCOPE','provider_mutations':0}
            request=urllib.request.Request(url,headers={'Authorization':'Bearer '+key,'Accept':'application/json'},method='GET')
            try:
                with opener.open(request,timeout=12) as response:raw=response.read(262145)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (301,302,307,308) and attempt==0:
                    target=urllib.parse.urljoin(url,exc.headers.get('Location',''))
                    if target==url or not allowed(target):return {'state':'HOLD_CLOUDCOPY_REDIRECT_SCOPE','provider_mutations':0}
                    url=target;continue
                return {'state':'HOLD_CLOUDCOPY_HTTP','http_status':int(exc.code),'provider_mutations':0}
        else:return {'state':'HOLD_CLOUDCOPY_REDIRECT_BOUND','provider_mutations':0}
        if len(raw)>262144:return {'state':'HOLD_CLOUDCOPY_RESPONSE_BOUND','provider_mutations':0}
        return summarize(json.loads(raw))
    except Exception:return {'state':'HOLD_CLOUDCOPY_UNAVAILABLE','provider_mutations':0}
