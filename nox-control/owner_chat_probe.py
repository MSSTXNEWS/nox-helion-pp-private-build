#!/usr/bin/env python3
"""Bounded owner-authenticated latency/UI probe; exports synthetic text only."""
import fcntl, hashlib, http.cookiejar, ipaddress, json, os, re, secrets, socket, struct, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path('/root/nox')
SITE=ROOT/'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
BASE='http://127.0.0.1:8080'

def nonloopback_base():
    for _,name in socket.if_nameindex():
        if name=='lo':continue
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                info=fcntl.ioctl(sock.fileno(),0x8915,struct.pack('256s',name.encode()[:15]))
            address=socket.inet_ntoa(info[20:24])
            if not ipaddress.ip_address(address).is_loopback:return 'http://'+address+':8080'
        except OSError:pass
    raise RuntimeError('HOLD_NONLOOPBACK_PEER_REQUIRED')

def emit(kind,value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},ensure_ascii=False,separators=(',',':')),flush=True)

def digest(data):return hashlib.sha256(data).hexdigest()

def redact(value):
    value=re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----','[REDACTED_PRIVATE_KEY]',value)
    value=re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@',r'\1[REDACTED]@',value)
    value=re.sub(r'(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}','[REDACTED]',value)
    return re.sub(r'(?im)^([^\n]*(?:password|secret|api_key|access_key|authorization|token)[\w\s]*=\s*)[\"\'][^\"\'\n]{12,}[\"\']',r'\1"[REDACTED]"',value)

def request(client,path,method='GET',data=None,timeout=6,base=None):
    payload=None if data is None else json.dumps(data,ensure_ascii=False).encode()
    req=urllib.request.Request((base or BASE)+path,data=payload,method=method,headers={'Content-Type':'application/json','Accept':'application/json'})
    try:return client.open(req,timeout=timeout)
    except urllib.error.HTTPError as exc:return exc

def obj(response,limit=100000):
    if response.status!=200:raise RuntimeError('HOLD_HTTP_'+str(response.status))
    raw=response.read(limit+1)
    if len(raw)>limit:raise RuntimeError('HOLD_RESPONSE_LIMIT')
    return json.loads(raw)

def meaningful_delta(text):
    return isinstance(text,str) and re.search(r'[^\s.…]',text) is not None

def history_matches_turns(messages, turns):
    """Verify every requested turn is present in the same durable dialog tail."""
    if not isinstance(messages, list) or len(messages) < len(turns) * 2:
        return False
    tail = messages[-len(turns) * 2:]
    for index, (prompt, answer) in enumerate(turns):
        user, assistant = tail[2 * index:2 * index + 2]
        if not isinstance(user, dict) or not isinstance(assistant, dict):
            return False
        if (user.get('role') != 'user' or assistant.get('role') != 'assistant'
                or user.get('content') != prompt or assistant.get('content') != answer):
            return False
    return True


def require_durable_result(saved, answered, phase):
    """A diagnostic run cannot emit COMPLETE after an unsuccessful chat turn."""
    if not saved or not answered:
        raise RuntimeError('HOLD_CHAT_PROBE_' + phase + '_NOT_ACCEPTED')


def require_executor_witness(done, messages, turns, owner_observed, model_matches):
    """Fail closed if an issued third chat turn is not persisted or disagrees with live owner state."""
    durable = (isinstance(done, dict) and done.get('saved') is True
               and done.get('s03_integrated') is True
               and history_matches_turns(messages, turns))
    if not (durable and owner_observed and model_matches):
        raise RuntimeError('HOLD_CHAT_PROBE_EXECUTOR_TURN_NOT_ACCEPTED')


def require_executor_turn_budget(elapsed_seconds):
    """Never report a completed multi-turn probe when its third POST was skipped."""
    if elapsed_seconds >= 210:
        raise RuntimeError('HOLD_CHAT_PROBE_EXECUTOR_TURN_BUDGET_EXHAUSTED')


def require_multiturn_requested(value):
    """Do not certify full multi-turn acceptance after only one chat turn."""
    if value != '1':
        raise RuntimeError('HOLD_CHAT_PROBE_MULTITURN_NOT_REQUESTED')


def numeric_public_answer(text):
    # Raw model text can unexpectedly draw on private memory. Export only a
    # bounded numeric answer to this synthetic arithmetic prompt, plus hashes.
    value=text.strip().strip('`*_ .!\n\r\t')
    return value if re.fullmatch(r'-?\d{1,6}',value or '') else '[NONNUMERIC_RESPONSE_WITHHELD]'

def consume_turn(client,prompt,dialog_id,timeout=95):
    started=time.monotonic()
    response=request(client,'/api/nox/chat/stream','POST',
        {'message':prompt,'history':[],'task':'general','dialog_id':dialog_id},timeout=timeout)
    if response.status!=200:
        response.close();raise RuntimeError('HOLD_STREAM_HTTP_'+str(response.status))
    events=[];answer='';done=None;first=None;placeholders=0;delta_count=0
    try:
        for index,line in enumerate(response):
            if index>2000 or len(line)>100000 or time.monotonic()-started>timeout+5:
                raise RuntimeError('HOLD_BOUNDED_STREAM')
            frame=json.loads(line)
            if not isinstance(frame,dict):raise RuntimeError('HOLD_STREAM_FRAME_SCHEMA')
            kind=frame.get('type');elapsed=round((time.monotonic()-started)*1000)
            if kind not in ('preparing','start','started','delta','done','error','status','meta'):
                raise RuntimeError('HOLD_STREAM_FRAME_TYPE')
            if not any(event['type']==kind for event in events):events.append({'type':kind,'ms':elapsed})
            if kind=='delta':
                text=frame.get('text','')
                if not isinstance(text,str):raise RuntimeError('HOLD_STREAM_DELTA_SCHEMA')
                if len(answer)+len(text)>10000:raise RuntimeError('HOLD_STREAM_TEXT_LIMIT')
                answer+=text;delta_count+=1
                if meaningful_delta(text):
                    if first is None:first=elapsed
                else:placeholders+=1
            elif kind=='done':
                if frame.get('dialog_id') != dialog_id:
                    raise RuntimeError('HOLD_STREAM_TERMINAL_DIALOG_MISMATCH')
                done=frame;break
            elif kind=='error':raise RuntimeError('HOLD_STREAM_ERROR')
            if len(answer)>10000:raise RuntimeError('HOLD_STREAM_TEXT_LIMIT')
    finally:response.close()
    if done is None or first is None:raise RuntimeError('HOLD_STREAM_INCOMPLETE_OR_PLACEHOLDER')
    return {'answer':answer,'done':done,'events':events,'first_meaningful_delta_ms':first,
            'placeholder_delta_count':placeholders,'delta_count':delta_count,
            'stream_total_ms':round((time.monotonic()-started)*1000)}

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
    global BASE
    if os.environ.get('NOX_PROBE_NONLOOPBACK','1')=='1':BASE=nonloopback_base()
    probe_started=time.monotonic()
    if os.environ.get('NOX_PROBE_SOURCE_EXPORT')=='1':sources()
    emit('chat_recent_timing',metrics())
    sys.path.insert(0,str(ROOT/'scripts'))
    import chat_proxy
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or len(password)<6:raise RuntimeError('HOLD_OWNER_CREDENTIAL_UNAVAILABLE')
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
    login=request(client,'/chat/login','POST',{'password':password});password=None
    if login.status!=200 or not any(True for _ in jar):raise RuntimeError('HOLD_OFFICIAL_LOGIN')
    login.close()
    try:
        report={'schema':'NOX_OWNER_CHAT_LATENCY_V1','private_data_exported':False,'paths':[],
                'nonloopback_peer':BASE!='http://127.0.0.1:8080','assets':[]}
        for path in ('/','/chat','/nox-web-v29/chat.html','/nox-web-v29/pc/resonance.html'):
            t=time.monotonic();r=request(client,path);raw=r.read(200000)
            text=raw.decode(errors='replace');title=re.search(r'<title[^>]*>(.*?)</title>',text,re.S|re.I)
            report['paths'].append({'path':path,'status':r.status,'final_path':urllib.parse.urlparse(r.url).path,'ms':round((time.monotonic()-t)*1000),
                'sha256':digest(raw),'title':title[1][:150] if title else None,'scripts':re.findall(r'<script[^>]+src=[\"\']([^\"\']+)',text)[:30]})
            if path=='/nox-web-v29/pc/resonance.html':
                resources=re.findall(r'<script[^>]+src=[\"\']([^\"\']+)',text)
                resources+=re.findall(r'<link[^>]+href=[\"\']([^\"\']+)',text)
                for resource in resources[:35]:
                    target=urllib.parse.urljoin(BASE+path,resource)
                    if urllib.parse.urlparse(target).netloc!=urllib.parse.urlparse(BASE).netloc:continue
                    local=urllib.parse.urlparse(target).path
                    with request(client,local) as asset:report['assets'].append({'path':local,'status':asset.status,'bytes_sampled':len(asset.read(100))})
        unauth=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        report['anonymous_http']={}
        for path in ('/api/nox/status','/api/ui/executors','/api/ui/events'):
            with request(unauth,path) as response:report['anonymous_http'][path]=response.status
        if report['nonloopback_peer']:
            if set(report['anonymous_http'].values())!={401}:raise RuntimeError('HOLD_ANONYMOUS_OWNER_SCOPE')
            status=obj(request(client,'/api/nox/status'))
            report['owner_status_bound']=status.get('native_p02_bound') is True
            executors=obj(request(client,'/api/ui/executors'))
            event_status=obj(request(client,'/api/ui/events?limit=1'))
            report['owner_events_access']=event_status.get('schema')=='NOX_OWNER_EVENTS_V1' and isinstance(event_status.get('events'),list)
            rows=executors.get('workers',[])
            report['owner_executors_access']=bool(executors.get('schema')=='NOX_OWNER_EXECUTORS_V1' and isinstance(rows,list))
            report['owner_executors']={'state':executors.get('state'),'configured':executors.get('configured'),
                'observed_workers':len(rows) if isinstance(rows,list) else None,
                'worker_ids':[str(row.get('id',''))[:60] for row in rows if isinstance(row,dict)] if isinstance(rows,list) else []}
        slot=obj(request(client,'/slots',base='http://127.0.0.1:8081'))
        report['slots']={'count':len(slot),'busy':sum(bool(s.get('is_processing',s.get('processing',False))) for s in slot)}
        emit('chat_before_probe',report)
        if not report['nonloopback_peer']:raise RuntimeError('HOLD_NONLOOPBACK_ACCEPTANCE_REQUIRED')
        if not report.get('owner_status_bound') or not report.get('owner_executors_access') or not report.get('owner_events_access'):
            raise RuntimeError('HOLD_AUTHENTICATED_OWNER_APIS')
        if (not report['assets'] or any(asset['status']!=200 or asset['bytes_sampled']==0 for asset in report['assets'])
                or any(page['status']!=200 for page in report['paths'])):
            raise RuntimeError('HOLD_RESONANCE_ASSET_HTTP')
        if report['slots']['busy']:raise RuntimeError('HOLD_CHAT_BUSY_FOR_SYNTHETIC_PROBE')
        # Single-turn diagnostics must not be reported as completed multi-turn acceptance.
        require_multiturn_requested(os.environ.get('NOX_PROBE_SECOND_TURN'))
        marker='nox_latency_'+secrets.token_hex(5)
        prompt='[QA '+marker+'] Сколько будет 17 умножить на 19? Ответь только числом.'
        dialog=obj(request(client,'/api/ui/memory/dialogs/create','POST',{'title':'NOX QA '+marker,'confirmed':True}))
        did=dialog.get('dialog_id')
        if not isinstance(did,str) or not re.fullmatch('[a-f0-9]{32}',did):raise RuntimeError('HOLD_DIALOG_CREATE')
        turn=consume_turn(client,prompt,did);answer=turn['answer'];receipt=turn['done']
        history=obj(request(client,'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6'))
        saved=bool(receipt and receipt.get('saved') is True and receipt.get('s03_integrated') is True
                   and history_matches_turns(history.get('messages'), [(prompt, answer)]))
        first=turn['first_meaningful_delta_ms']
        emit('chat_synthetic_latency',{'events':turn['events'],'total_ms':turn['stream_total_ms'],
            'first_meaningful_delta_ms':first,'placeholder_delta_count':turn['placeholder_delta_count'],
            'delta_count':turn['delta_count'],'answer_public_synthetic':numeric_public_answer(answer),
            'answer_sha256':digest(answer.encode()),'saved_verified':saved,
            'arithmetic_pass':numeric_public_answer(answer)=='323',
            'performance_target_pass':first<=8000 and turn['stream_total_ms']<=25000})
        require_durable_result(saved, numeric_public_answer(answer)=='323', 'FIRST_TURN')
        if os.environ.get('NOX_PROBE_SECOND_TURN')=='1':
            followup='Какое число ты только что получил? Ответь только этим числом.'
            follow=consume_turn(client,followup,did);answer2=follow['answer'];done=follow['done']
            stored=obj(request(client,'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6')).get('messages',[])
            passed=bool(done and done.get('saved') is True and done.get('s03_integrated') is True
                        and history_matches_turns(stored, [(prompt, answer), (followup, answer2)]))
            emit('chat_history_followup',{'history_model_pass':passed,'client_history_empty':True,
                'first_delta_ms':follow['first_meaningful_delta_ms'],'first_meaningful_delta_ms':follow['first_meaningful_delta_ms'],
                'total_ms':follow['stream_total_ms'],'answer_public_synthetic':numeric_public_answer(answer2),
                'answer_sha256':digest(answer2.encode()),
                'performance_target_pass':follow['first_meaningful_delta_ms']<=5000 and follow['stream_total_ms']<=25000})
            require_durable_result(passed, numeric_public_answer(answer2)=='323', 'SECOND_TURN')
            require_executor_turn_budget(time.monotonic()-probe_started)
            question='Сколько сейчас исполнителей и агентов у NOX?'
            turn3=consume_turn(client,question,did,timeout=30)
            text=turn3['answer'];end=turn3['done']
            fresh=obj(request(client,'/api/ui/executors'))
            rows=fresh.get('workers',[])
            count=bool(fresh.get('state')=='OBSERVED' and fresh.get('configured')==6 and isinstance(rows,list) and len(rows)==6
                       and len({row.get('id') for row in rows if isinstance(row,dict)})==6)
            phrase=bool(re.search(r'настроено\s+6\s+исполнител',text,re.I)
                        and re.search(r'6\s+исполнителей\s*\+\s*NOX',text))
            third_history=obj(request(client,'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=8')).get('messages',[])
            expected_three=[(prompt,answer),(followup,answer2),(question,text)]
            third_durable=(isinstance(end,dict) and end.get('saved') is True
                           and end.get('s03_integrated') is True
                           and history_matches_turns(third_history,expected_three))
            emit('chat_executor_question',{'verified_six_plus_nox':bool(count and phrase and third_durable),
                'live_api_fresh':count,'native_answer_matches_six_plus_nox':phrase,
                'saved':end.get('saved') is True,'s03_integrated':end.get('s03_integrated') is True,
                'three_turn_history_verified':third_durable,
                'first_meaningful_delta_ms':turn3['first_meaningful_delta_ms'],
                'answer_sha256':digest(text.encode()),'raw_answer_exported':False})
            require_executor_witness(end,third_history,expected_three,count,phrase)
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
