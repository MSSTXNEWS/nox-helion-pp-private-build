#!/usr/bin/env python3
"""Bounded owner-authenticated latency/UI probe; exports synthetic text only."""
import hashlib, http.cookiejar, json, os, re, secrets, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path('/root/nox')
SITE=ROOT/'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
BASE='http://127.0.0.1:8080'

def emit(kind,value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},ensure_ascii=False,separators=(',',':')),flush=True)

def digest(data):return hashlib.sha256(data).hexdigest()

def redact(value):
    value=re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----','[REDACTED_PRIVATE_KEY]',value)
    value=re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@',r'\1[REDACTED]@',value)
    value=re.sub(r'(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}','[REDACTED]',value)
    return re.sub(r'(?im)^([^\n]*(?:password|secret|api_key|access_key|authorization|token)[\w\s]*=\s*)[\"\'][^\"\'\n]{12,}[\"\']',r'\1"[REDACTED]"',value)

def request(client,path,method='GET',data=None,timeout=6,base=BASE):
    payload=None if data is None else json.dumps(data,ensure_ascii=False).encode()
    req=urllib.request.Request(base+path,data=payload,method=method,headers={'Content-Type':'application/json','Accept':'application/json'})
    try:return client.open(req,timeout=timeout)
    except urllib.error.HTTPError as exc:return exc

def obj(response,limit=100000):
    if response.status!=200:raise RuntimeError('HOLD_HTTP_'+str(response.status))
    raw=response.read(limit+1)
    if len(raw)>limit:raise RuntimeError('HOLD_RESPONSE_LIMIT')
    return json.loads(raw)

def sources():
    for rel in ('scripts/agent_loop.py','scripts/slim_chat_t885u.py','scripts/understanding/hook.py','scripts/understanding_hook.py'):
        path=ROOT/rel
        if not path.is_file() or path.is_symlink():continue
        raw=path.read_bytes()
        if len(raw)>125000:
            emit('chat_source',{'path':str(path),'sha256':digest(raw),'bytes':len(raw),'source_omitted':True});continue
        source=raw.decode(errors='replace');safe=redact(source)
        emit('chat_source',{'path':str(path),'sha256':digest(raw),'bytes':len(raw),'source_redacted':safe!=source,'source':safe})
    for rel in ('scripts/chat.html','scripts/nox_v29_chat_bridge.py','scripts/chat_proxy.py'):
        p=ROOT/rel
        if p.is_file():emit('chat_source_pin',{'path':str(p),'sha256':digest(p.read_bytes()),'bytes':p.stat().st_size})
    for rel in ('chat.html','nox-chat.js','nox-ui.js','native-owner.js','pc/resonance.html','pc/v22/resonance.template.html'):
        p=SITE/rel
        if not p.is_file():continue
        raw=p.read_bytes()
        emit('chat_asset',{'path':str(p),'sha256':digest(raw),'bytes':len(raw),'v135':b'nox-v135' in raw,'v137':b'nox-v137' in raw,
                          'source':raw.decode(errors='replace') if rel.endswith('resonance.html') and len(raw)<70000 else None})

def metrics():
    path=ROOT/'logs/proxy.log'
    if not path.is_file():return []
    with path.open('rb') as f:
        f.seek(max(0,path.stat().st_size-160000));data=f.read().decode(errors='replace')
    rows=[]
    for line in data.splitlines():
        values=re.findall(r'\b(augment_ms|s03_ms|retrieve_ms|enrich_ms|searx_ms|build_ms|llm_ms|total_ms|ttft_s|infinite_ms|cedr_ready|cache_prompt)=([0-9.]+|True|False|None)',line)
        if values:rows.append(dict(values))
    return rows[-35:]

def main():
    sources();emit('chat_recent_timing',metrics())
    sys.path.insert(0,str(ROOT/'scripts'))
    import chat_proxy
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or len(password)<6:raise RuntimeError('HOLD_OWNER_CREDENTIAL_UNAVAILABLE')
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login=request(client,'/chat/login','POST',{'password':password});password=None
    if login.status!=200 or not any(True for _ in jar):raise RuntimeError('HOLD_OFFICIAL_LOGIN')
    try:
        report={'schema':'NOX_OWNER_CHAT_LATENCY_V1','private_data_exported':False,'paths':[]}
        for path in ('/','/chat','/nox-web-v29/chat.html','/nox-web-v29/pc/resonance.html'):
            t=time.monotonic();r=request(client,path);raw=r.read(200000)
            text=raw.decode(errors='replace');title=re.search(r'<title[^>]*>(.*?)</title>',text,re.S|re.I)
            report['paths'].append({'path':path,'status':r.status,'final_path':urllib.parse.urlparse(r.url).path,'ms':round((time.monotonic()-t)*1000),
                'sha256':digest(raw),'title':title[1][:150] if title else None,'scripts':re.findall(r'<script[^>]+src=[\"\']([^\"\']+)',text)[:30]})
        slot=obj(request(client,'/slots',base='http://127.0.0.1:8081'))
        report['slots']={'count':len(slot),'busy':sum(bool(s.get('is_processing',s.get('processing',False))) for s in slot)}
        emit('chat_before_probe',report)
        if report['slots']['busy']:raise RuntimeError('HOLD_CHAT_BUSY_FOR_SYNTHETIC_PROBE')
        marker='nox_latency_'+secrets.token_hex(5)
        prompt='[QA '+marker+'] Сколько будет 17 умножить на 19? Ответь только числом.'
        dialog=obj(request(client,'/api/ui/memory/dialogs/create','POST',{'title':'NOX QA '+marker,'confirmed':True}))
        did=dialog.get('dialog_id')
        if not isinstance(did,str) or not re.fullmatch('[a-f0-9]{32}',did):raise RuntimeError('HOLD_DIALOG_CREATE')
        t=time.monotonic();r=request(client,'/api/nox/chat/stream','POST',{'message':prompt,'history':[],'task':'general','dialog_id':did},timeout=95)
        events=[];answer='';receipt=None
        if r.status!=200:raise RuntimeError('HOLD_STREAM_HTTP_'+str(r.status))
        try:
            for i,line in enumerate(r):
                if i>2000 or len(line)>100000:raise RuntimeError('HOLD_BOUNDED_STREAM')
                frame=json.loads(line);kind=frame.get('type');ms=round((time.monotonic()-t)*1000)
                if not any(e['type']==kind for e in events):events.append({'type':kind,'ms':ms})
                if kind=='delta':answer+=frame.get('text','')
                elif kind=='done':receipt=frame;break
                elif kind=='error':raise RuntimeError(str(frame.get('error','HOLD_STREAM_ERROR'))[:100])
                if len(answer)>10000 or time.monotonic()-t>105:raise RuntimeError('HOLD_STREAM_DEADLINE')
        finally:r.close()
        history=obj(request(client,'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6'))
        pair=history.get('messages',[])[-2:]
        saved=bool(receipt and receipt.get('saved') is True and receipt.get('s03_integrated') is True and len(pair)==2 and pair[0].get('content')==prompt and pair[1].get('content')==answer)
        emit('chat_synthetic_latency',{'events':events,'total_ms':round((time.monotonic()-t)*1000),'answer_public_synthetic':answer[:4000],
                                     'saved_verified':saved,'arithmetic_pass':bool(re.search(r'(?<!\d)323(?!\d)',answer))})
        emit('chat_recent_timing_after',metrics())
    finally:
        try:request(client,'/chat/logout','POST',{}).close()
        except Exception:pass
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        reason=str(exc);emit('chat_probe_hold',{'reason':reason if re.fullmatch('[A-Z0-9_]{1,120}',reason) else type(exc).__name__})
        raise SystemExit(2)
