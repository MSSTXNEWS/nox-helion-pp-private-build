#!/usr/bin/env python3
"""Bounded owner-authenticated latency/UI probe; exports synthetic text only."""
import fcntl, hashlib, http.cookiejar, ipaddress, json, math, os, re, secrets, socket, struct, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
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

class RejectPostRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow an HTTP redirect after issuing a non-idempotent request.

    In particular an HTTP 302 could transform a chat POST into a second request
    at an unrelated URL *before* the final stream-target fence could run.
    Keep GET redirect behavior unchanged for explicit final-URL diagnostics.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.get_method() != 'GET':
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(client,path,method='GET',data=None,timeout=6,base=None):
    payload=None if data is None else json.dumps(data,ensure_ascii=False).encode()
    req=urllib.request.Request((base or BASE)+path,data=payload,method=method,headers={'Content-Type':'application/json','Accept':'application/json'})
    try:return client.open(req,timeout=timeout)
    except urllib.error.HTTPError as exc:return exc

def obj(response,limit=100000):
    """Bounded owner JSON readback; always release its HTTP response/socket."""
    try:
        if response.status!=200:raise RuntimeError('HOLD_HTTP_'+str(response.status))
        raw=response.read(limit+1)
        if len(raw)>limit:raise RuntimeError('HOLD_RESPONSE_LIMIT')
        return json.loads(raw, parse_constant=reject_owner_nonfinite_json_constant,
                          parse_float=reject_owner_nonfinite_json_float,
                          object_pairs_hook=reject_owner_duplicate_json_keys)
    finally:
        response.close()


def reject_owner_nonfinite_json_constant(_value):
    """Do not certify owner APIs carrying nonstandard JSON constants."""
    raise RuntimeError('HOLD_OWNER_JSON_NONFINITE')


def reject_owner_nonfinite_json_float(value):
    """Exponent-overflow JSON floats can silently become Infinity in Python."""
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError('HOLD_OWNER_JSON_NONFINITE')
    return number


def reject_owner_duplicate_json_keys(pairs):
    """Fail closed on ambiguous owner status/history keys at any nesting level."""
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise RuntimeError('HOLD_OWNER_JSON_DUPLICATE_KEY')
        fields[key] = value
    return fields

def require_same_origin_target(response, requested_path, exact_path=True):
    """A redirected login/foreign page must never count as healthy UI or JS."""
    actual = urllib.parse.urlsplit(response.url)
    expected = urllib.parse.urlsplit(BASE)
    if actual.scheme != expected.scheme or actual.netloc != expected.netloc:
        raise RuntimeError('HOLD_CHAT_RESPONSE_ORIGIN')
    if exact_path and actual.path != requested_path:
        raise RuntimeError('HOLD_CHAT_RESPONSE_REDIRECT')


def require_exact_asset_target(response, requested_path_and_query):
    """Inspect the same cache/versioned asset URL that the browser requested."""
    requested = urllib.parse.urlsplit(requested_path_and_query)
    require_same_origin_target(response, requested.path)
    if urllib.parse.urlsplit(response.url).query != requested.query:
        raise RuntimeError('HOLD_RESONANCE_ASSET_QUERY_MISMATCH')


def require_exact_stream_target(response):
    """Redirected/cross-origin HTTP 200 must not certify the active chat stream."""
    actual = urllib.parse.urlsplit(response.url)
    expected = urllib.parse.urlsplit(BASE)
    if actual.scheme != expected.scheme or actual.netloc != expected.netloc:
        raise RuntimeError('HOLD_STREAM_RESPONSE_ORIGIN')
    if (actual.path != '/api/nox/chat/stream' or actual.query or actual.fragment):
        raise RuntimeError('HOLD_STREAM_RESPONSE_REDIRECT')


def require_not_html_asset(response, sample):
    """HTTP 200 SPA/login HTML at a JS/CSS path is not a usable Resonance asset."""
    headers = getattr(response, 'headers', None)
    ctype = headers.get('Content-Type', '') if headers is not None else ''
    if not isinstance(ctype, str):
        raise RuntimeError('HOLD_RESONANCE_ASSET_HTML_FALLBACK')
    media = ctype.split(';', 1)[0].strip().lower()
    prefix = sample.lstrip(b'\xef\xbb\xbf \t\r\n')
    if (media in ('text/html', 'application/xhtml+xml')
            or re.match(rb'(?i)^(?:<!doctype\s+html\b|<html\b|<head\b|<body\b)', prefix)):
        raise RuntimeError('HOLD_RESONANCE_ASSET_HTML_FALLBACK')


def require_browser_asset_mime(response, path):
    """A 200 JSON/error response is not an executable JS/CSS asset in the browser."""
    headers = getattr(response, 'headers', None)
    ctype = headers.get('Content-Type', '') if headers is not None else ''
    if not isinstance(ctype, str):
        raise RuntimeError('HOLD_RESONANCE_ASSET_MIME')
    media = ctype.split(';', 1)[0].strip().lower()
    extension = urllib.parse.urlsplit(path).path.lower()
    expected = ({'text/css'} if extension.endswith('.css') else
                {'text/javascript', 'application/javascript', 'application/x-javascript'}
                if extension.endswith(('.js', '.mjs')) else set())
    if media not in expected:
        raise RuntimeError('HOLD_RESONANCE_ASSET_MIME')


def page_snapshot(response, limit=200000, expected_path=None):
    """Read a complete bounded owner HTML page and always close its socket."""
    try:
        status = response.status
        require_same_origin_target(response, expected_path, expected_path is not None)
        path = urllib.parse.urlparse(response.url).path
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise RuntimeError('HOLD_CHAT_PAGE_LIMIT')
        return status, path, raw
    finally:
        response.close()


def meaningful_delta(text):
    """Only visible glyphs may start meaningful-stream TTFT; ignore invisible format/mark/control placeholders."""
    return isinstance(text, str) and any(
        ch not in '.…' and unicodedata.category(ch)[0] not in ('C', 'M', 'Z')
        for ch in text
    )

def history_matches_turns(messages, turns, dialog_id=None):
    """Verify ordered roles/content and any present row-level dialog identity."""
    if not isinstance(messages, list) or len(messages) < len(turns) * 2:
        return False
    tail = messages[-len(turns) * 2:]
    for index, (prompt, answer) in enumerate(turns):
        user, assistant = tail[2 * index:2 * index + 2]
        if not isinstance(user, dict) or not isinstance(assistant, dict):
            return False
        if dialog_id is not None and any('dialog_id' in row and row['dialog_id'] != dialog_id
                                         for row in (user, assistant)):
            return False
        if (user.get('role') != 'user' or assistant.get('role') != 'assistant'
                or user.get('content') != prompt or assistant.get('content') != answer):
            return False
    return True


def scoped_history_matches_turns(history, turns, dialog_id):
    """Reject a mismatched history session even when its visible rows match."""
    if not isinstance(history, dict) or history.get('dialog_id') != dialog_id:
        return False
    return history_matches_turns(history.get('messages'), turns, dialog_id)


def require_durable_result(saved, answered, phase):
    """A diagnostic run cannot emit COMPLETE after an unsuccessful chat turn."""
    if not saved or not answered:
        raise RuntimeError('HOLD_CHAT_PROBE_' + phase + '_NOT_ACCEPTED')


def require_executor_witness(done, messages, turns, owner_observed, model_matches, dialog_id=None):
    """Fail closed if an issued third chat turn is not persisted or disagrees with live owner state."""
    durable = (isinstance(done, dict) and done.get('saved') is True
               and done.get('s03_integrated') is True
               and (scoped_history_matches_turns(messages, turns, dialog_id) if dialog_id is not None
                    else history_matches_turns(messages, turns)))
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


def require_latency_target(turn, phase, first_limit_ms):
    """Fail closed when the already-advertised browser latency target is missed."""
    first = turn.get('first_meaningful_delta_ms') if isinstance(turn, dict) else None
    total = turn.get('stream_total_ms') if isinstance(turn, dict) else None
    valid = (type(first) in (int, float) and type(total) in (int, float)
             and 0 <= first <= first_limit_ms and first <= total <= 25000)
    if not valid:
        raise RuntimeError('HOLD_CHAT_PROBE_' + phase + '_LATENCY_TARGET')


def numeric_public_answer(text):
    # Raw model text can unexpectedly draw on private memory. Export only a
    # bounded numeric answer to this synthetic arithmetic prompt, plus hashes.
    value=text.strip().strip('`*_ .!\n\r\t')
    return value if re.fullmatch(r'-?\d{1,6}',value or '') else '[NONNUMERIC_RESPONSE_WITHHELD]'

def reject_nonfinite_json_constant(_value):
    """Strict NDJSON: Python's default json.loads incorrectly accepts NaN/Infinity."""
    raise RuntimeError('HOLD_STREAM_NONFINITE_JSON')


def reject_nonfinite_json_float(value):
    """Do not certify an SSE JSON exponent overflow as valid finite metadata."""
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError('HOLD_STREAM_NONFINITE_JSON')
    return number


def reject_duplicate_json_keys(pairs):
    """Reject ambiguous NDJSON fields instead of accepting Python's last-key-wins result."""
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise RuntimeError('HOLD_STREAM_DUPLICATE_JSON_KEY')
        fields[key] = value
    return fields


def stream_status_is_failure(value):
    """Fail closed for known failure labels and HTTP failure status values."""
    if isinstance(value, str):
        status = value.strip().lower()
        return status in ('error', 'failed', 'cancelled', 'aborted') or (
            status.isdecimal() and int(status) >= 400)
    return type(value) is int and value >= 400


def stream_frame_reports_failure(frame):
    """Recognize HTTP failures in flat and structured upstream status metadata.

    A downstream saved=true DONE must not erase an earlier 4xx/5xx emitted in
    a status object or an alternate HTTP status field.
    """
    keys = ('code', 'status_code', 'statusCode', 'http_status', 'httpStatus')
    status = frame.get('status')
    if stream_status_is_failure(status):
        return True
    if isinstance(status, dict):
        # A structured status can carry an upstream failure without HTTP code.
        # Do not let a later saved=true done erase nested error/success=false.
        if status.get('error') not in (None, '', False) or status.get('success') is False:
            return True
        if any(stream_status_is_failure(status.get(key))
               for key in (*keys, 'status', 'state')):
            return True
    return any(stream_status_is_failure(frame.get(key)) for key in keys)


def bounded_stream_lines(response, max_line=100000):
    """Bound each network read; iteration can buffer a huge NDJSON line before a length check."""
    readline = getattr(response, 'readline', None)
    if not callable(readline):
        raise RuntimeError('HOLD_STREAM_BOUNDED_READER_UNAVAILABLE')
    while True:
        line = readline(max_line + 1)
        if line == b'':
            return
        if not isinstance(line, bytes) or len(line) > max_line:
            raise RuntimeError('HOLD_BOUNDED_STREAM')
        yield line


def consume_turn(client,prompt,dialog_id,timeout=95):
    started=time.monotonic()
    response=request(client,'/api/nox/chat/stream','POST',
        {'message':prompt,'history':[],'task':'general','dialog_id':dialog_id},timeout=timeout)
    if response.status!=200:
        response.close();raise RuntimeError('HOLD_STREAM_HTTP_'+str(response.status))
    events=[];answer='';done=None;first=None;placeholders=0;delta_count=0
    try:
        require_exact_stream_target(response)
        for index,line in enumerate(bounded_stream_lines(response)):
            if index>2000 or len(line)>100000 or time.monotonic()-started>timeout+5:
                raise RuntimeError('HOLD_BOUNDED_STREAM')
            if done is not None:raise RuntimeError('HOLD_STREAM_TRAILING_AFTER_DONE')
            if not isinstance(line, bytes) or not line.endswith(b'\n'):
                raise RuntimeError('HOLD_STREAM_MISSING_NEWLINE')
            frame=json.loads(line, parse_constant=reject_nonfinite_json_constant,
                             parse_float=reject_nonfinite_json_float,
                             object_pairs_hook=reject_duplicate_json_keys)
            if not isinstance(frame,dict):raise RuntimeError('HOLD_STREAM_FRAME_SCHEMA')
            kind=frame.get('type');elapsed=round((time.monotonic()-started)*1000)
            if kind not in ('preparing','start','started','delta','done','error','status','meta'):
                raise RuntimeError('HOLD_STREAM_FRAME_TYPE')
            # A preterminal failure must poison the entire stream, even if
            # the backend subsequently emits a successful saved=true done.
            if kind not in ('done', 'error') and (
                    frame.get('error') not in (None, '', False)
                    or stream_frame_reports_failure(frame)
                    or frame.get('success') is False):
                raise RuntimeError('HOLD_STREAM_PRETERMINAL_FAILURE')
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
                # A terminal frame carrying a failure cannot certify saved history.
                # Some upstreams report an error *inside* done instead of a
                # separate type=error event; never trust its success flags.
                if (frame.get('error') not in (None, '', False)
                        or stream_frame_reports_failure(frame)
                        or frame.get('success') is False):
                    raise RuntimeError('HOLD_STREAM_TERMINAL_FAILURE')
                if frame.get('dialog_id') != dialog_id:
                    raise RuntimeError('HOLD_STREAM_TERMINAL_DIALOG_MISMATCH')
                done=frame  # Require clean EOF after exactly one terminal frame.
            elif kind=='error':raise RuntimeError('HOLD_STREAM_ERROR')
            if len(answer)>10000:raise RuntimeError('HOLD_STREAM_TEXT_LIMIT')
    finally:response.close()
    if done is None or first is None:raise RuntimeError('HOLD_STREAM_INCOMPLETE_OR_PLACEHOLDER')
    return {'answer':answer,'done':done,'events':events,'first_meaningful_delta_ms':first,
            'placeholder_delta_count':placeholders,'delta_count':delta_count,
            'stream_total_ms':round((time.monotonic()-started)*1000)}

def admitted_consume_turn(client, prompt, dialog_id, timeout=95):
    """Re-admit RAM immediately before EVERY synthetic model-stream POST.

    An earlier turn can consume cgroup headroom before the next turn; the
    one-time check before dialog creation does not authorize all later POSTs.
    This is not a replacement for native owner/CAS, STOP, VRAM or lease gates.
    """
    require_cgroup_probe_headroom()
    # Another owner may take the model slot between synthetic chat turns.
    # An earlier idle snapshot never authorizes the next non-idempotent POST.
    slots = model_slots_state(client)
    if slots['busy']:
        raise RuntimeError('HOLD_CHAT_BUSY_FOR_SYNTHETIC_PROBE')
    return consume_turn(client, prompt, dialog_id, timeout=timeout)


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

def require_exact_model_slots_target(response):
    """A redirected /slots JSON must never authorize a new model POST."""
    actual = urllib.parse.urlsplit(response.url)
    if (actual.scheme, actual.netloc, actual.path, actual.query, actual.fragment) != (
            'http', '127.0.0.1:8098', '/slots', '', ''):
        raise RuntimeError('HOLD_CHAT_SLOTS_RESPONSE_ROUTE')


def model_slots_state(client):
    """Read only the active model slots. Unknown/missing state is never idle."""
    try:
        with request(client, '/slots', base='http://127.0.0.1:8098') as response:
            require_exact_model_slots_target(response)
            slots = obj(response, limit=100000)
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError('HOLD_CHAT_SLOTS_ENDPOINT_UNAVAILABLE') from exc
    if not isinstance(slots, list) or not slots or len(slots) > 1024:
        raise RuntimeError('HOLD_CHAT_SLOTS_STATE_UNVERIFIED')
    busy = 0
    for slot in slots:
        if not isinstance(slot, dict):
            raise RuntimeError('HOLD_CHAT_SLOTS_STATE_UNVERIFIED')
        flags = [slot[key] for key in ('is_processing', 'processing') if key in slot]
        if (not flags or any(type(flag) is not bool for flag in flags)
                or len(set(flags)) != 1):
            raise RuntimeError('HOLD_CHAT_SLOTS_STATE_UNVERIFIED')
        busy += int(flags[0])
    return {'count': len(slots), 'busy': busy}


def observed_owner_executor_count(snapshot):
    """Bind the third synthetic answer to CURRENT observed native workers.

    Configured workers are not permanently six; owner observations can be three.
    Any missing, inconsistent, or duplicate worker identity remains unverified.
    """
    if not isinstance(snapshot, dict) or snapshot.get('schema') != 'NOX_OWNER_EXECUTORS_V1':
        return None
    configured = snapshot.get('configured')
    workers = snapshot.get('workers')
    if (snapshot.get('state') != 'OBSERVED'
            or type(configured) is not int or not 1 <= configured <= 64
            or not isinstance(workers, list) or len(workers) != configured):
        return None
    identifiers = []
    for row in workers:
        if not isinstance(row, dict):
            return None
        identity = row.get('id')
        if (not (isinstance(identity, str) and 0 < len(identity) <= 128)
                and not (type(identity) is int and identity >= 0)):
            return None
        identifiers.append(identity)
    if len(set(identifiers)) != configured:
        return None
    return configured


def answer_matches_observed_executor_count(answer, configured):
    """The model's N executors + NOX claim must match the observed N."""
    if not isinstance(answer, str) or type(configured) is not int or configured < 1:
        return False
    mentioned = [int(value) for value in re.findall(
        r'(?<!\d)(\d{1,3})\s+исполнител[а-яё]*\b', answer, re.I)]
    return (bool(mentioned) and all(value == configured for value in mentioned)
            and re.search(r'(?:\+|и)\s*NOX\b', answer, re.I) is not None)


def require_cgroup_probe_headroom(
        limit_path=Path('/sys/fs/cgroup/memory.max'),
        current_path=Path('/sys/fs/cgroup/memory.current'),
        minimum_bytes=2 * 1024 ** 3):
    """Fail closed before synthetic dialog/chat writes when NOX cgroup RAM is too low.

    This read-only cgroup-v2 check is only one admission fence. It does not
    replace the independent native owner/CAS, STOP, lease, VRAM and rollback gates.
    """
    try:
        raw_limit = limit_path.read_text().strip()
        raw_current = current_path.read_text().strip()
        if not raw_limit.isdecimal() or not raw_current.isdecimal():
            raise ValueError('unbounded or malformed cgroup counters')
        limit = int(raw_limit)
        current = int(raw_current)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        raise RuntimeError('HOLD_CHAT_PROBE_CGROUP_RAM_ADMISSION') from exc
    if limit <= 0 or current > limit or limit - current < minimum_bytes:
        raise RuntimeError('HOLD_CHAT_PROBE_CGROUP_RAM_ADMISSION')
    return limit - current


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
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar),RejectPostRedirect())
    login=request(client,'/chat/login','POST',{'password':password});password=None
    if login.status!=200 or not any(True for _ in jar):raise RuntimeError('HOLD_OFFICIAL_LOGIN')
    login.close()
    try:
        report={'schema':'NOX_OWNER_CHAT_LATENCY_V1','private_data_exported':False,'paths':[],
                'nonloopback_peer':BASE!='http://127.0.0.1:8080','assets':[]}
        for path in ('/','/chat','/nox-web-v29/chat.html','/nox-web-v29/pc/resonance.html'):
            t=time.monotonic();status,final_path,raw=page_snapshot(request(client,path), expected_path=path if path != '/' else None)
            text=raw.decode(errors='replace');title=re.search(r'<title[^>]*>(.*?)</title>',text,re.S|re.I)
            report['paths'].append({'path':path,'status':status,'final_path':final_path,'ms':round((time.monotonic()-t)*1000),
                'sha256':digest(raw),'title':title[1][:150] if title else None,'scripts':re.findall(r'<script[^>]+src=[\"\']([^\"\']+)',text)[:30]})
            if path=='/nox-web-v29/pc/resonance.html':
                resources=re.findall(r'<script[^>]+src=[\"\']([^\"\']+)',text)
                resources+=re.findall(r'<link[^>]+href=[\"\']([^\"\']+)',text)
                for resource in resources[:35]:
                    target=urllib.parse.urljoin(BASE+path,resource)
                    if urllib.parse.urlparse(target).netloc!=urllib.parse.urlparse(BASE).netloc:continue
                    target_parts=urllib.parse.urlsplit(target)
                    local=target_parts.path
                    asset_request=local + ('?' + target_parts.query if target_parts.query else '')
                    with request(client,asset_request) as asset:
                        require_exact_asset_target(asset,asset_request)
                        sample = asset.read(512)
                        if asset.status == 200 and local.lower().endswith(('.js', '.mjs', '.css')):
                            require_not_html_asset(asset, sample)
                            require_browser_asset_mime(asset, local)
                        report['assets'].append({'path':local,'status':asset.status,'bytes_sampled':len(sample)})
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
        report['slots']=model_slots_state(client)
        emit('chat_before_probe',report)
        if not report['nonloopback_peer']:raise RuntimeError('HOLD_NONLOOPBACK_ACCEPTANCE_REQUIRED')
        if not report.get('owner_status_bound') or not report.get('owner_executors_access') or not report.get('owner_events_access'):
            raise RuntimeError('HOLD_AUTHENTICATED_OWNER_APIS')
        if (not report['assets'] or any(asset['status']!=200 or asset['bytes_sampled']==0 for asset in report['assets'])
                or any(page['status']!=200 for page in report['paths'])):
            raise RuntimeError('HOLD_RESONANCE_ASSET_HTTP')
        if report['slots']['busy']:raise RuntimeError('HOLD_CHAT_BUSY_FOR_SYNTHETIC_PROBE')
        require_cgroup_probe_headroom()  # Before ANY synthetic dialog-create/chat POST.
        # Single-turn diagnostics must not be reported as completed multi-turn acceptance.
        require_multiturn_requested(os.environ.get('NOX_PROBE_SECOND_TURN'))
        marker='nox_latency_'+secrets.token_hex(5)
        prompt='[QA '+marker+'] Сколько будет 17 умножить на 19? Ответь только числом.'
        dialog=obj(request(client,'/api/ui/memory/dialogs/create','POST',{'title':'NOX QA '+marker,'confirmed':True}))
        did=dialog.get('dialog_id')
        if not isinstance(did,str) or not re.fullmatch('[a-f0-9]{32}',did):raise RuntimeError('HOLD_DIALOG_CREATE')
        turn=admitted_consume_turn(client,prompt,did);answer=turn['answer'];receipt=turn['done']
        history=obj(request(client,'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6'))
        saved=bool(receipt and receipt.get('saved') is True and receipt.get('s03_integrated') is True
                   and scoped_history_matches_turns(history, [(prompt, answer)], did))
        first=turn['first_meaningful_delta_ms']
        emit('chat_synthetic_latency',{'events':turn['events'],'total_ms':turn['stream_total_ms'],
            'first_meaningful_delta_ms':first,'placeholder_delta_count':turn['placeholder_delta_count'],
            'delta_count':turn['delta_count'],'answer_public_synthetic':numeric_public_answer(answer),
            'answer_sha256':digest(answer.encode()),'saved_verified':saved,
            'arithmetic_pass':numeric_public_answer(answer)=='323',
            'performance_target_pass':first<=8000 and turn['stream_total_ms']<=25000})
        require_durable_result(saved, numeric_public_answer(answer)=='323', 'FIRST_TURN')
        require_latency_target(turn, 'FIRST_TURN', 8000)
        if os.environ.get('NOX_PROBE_SECOND_TURN')=='1':
            followup='Какое число ты только что получил? Ответь только этим числом.'
            follow=admitted_consume_turn(client,followup,did);answer2=follow['answer'];done=follow['done']
            stored=obj(request(client,'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6'))
            passed=bool(done and done.get('saved') is True and done.get('s03_integrated') is True
                        and scoped_history_matches_turns(stored, [(prompt, answer), (followup, answer2)], did))
            emit('chat_history_followup',{'history_model_pass':passed,'client_history_empty':True,
                'first_delta_ms':follow['first_meaningful_delta_ms'],'first_meaningful_delta_ms':follow['first_meaningful_delta_ms'],
                'total_ms':follow['stream_total_ms'],'answer_public_synthetic':numeric_public_answer(answer2),
                'answer_sha256':digest(answer2.encode()),
                'performance_target_pass':follow['first_meaningful_delta_ms']<=5000 and follow['stream_total_ms']<=25000})
            require_durable_result(passed, numeric_public_answer(answer2)=='323', 'SECOND_TURN')
            require_latency_target(follow, 'SECOND_TURN', 5000)
            require_executor_turn_budget(time.monotonic()-probe_started)
            question='Сколько сейчас исполнителей и агентов у NOX?'
            turn3=admitted_consume_turn(client,question,did,timeout=30)
            text=turn3['answer'];end=turn3['done']
            fresh=obj(request(client,'/api/ui/executors'))
            configured=observed_owner_executor_count(fresh)
            count=configured is not None
            phrase=answer_matches_observed_executor_count(text, configured)
            third_history=obj(request(client,'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=8'))
            expected_three=[(prompt,answer),(followup,answer2),(question,text)]
            third_durable=(isinstance(end,dict) and end.get('saved') is True
                           and end.get('s03_integrated') is True
                           and scoped_history_matches_turns(third_history,expected_three,did))
            emit('chat_executor_question',{'verified_six_plus_nox':bool(configured == 6 and phrase and third_durable),
                'verified_observed_executor_count':bool(count and phrase and third_durable),
                'observed_configured_count':configured,
                'live_api_fresh':count,'native_answer_matches_six_plus_nox':bool(configured == 6 and phrase),
                'native_answer_matches_observed_count':phrase,
                'saved':end.get('saved') is True,'s03_integrated':end.get('s03_integrated') is True,
                'three_turn_history_verified':third_durable,
                'first_meaningful_delta_ms':turn3['first_meaningful_delta_ms'],
                'answer_sha256':digest(text.encode()),'raw_answer_exported':False})
            require_executor_witness(end,third_history,expected_three,count,phrase,did)
            # Third inference and durable-history readback also consume the 210 s budget.
            # A passed pre-POST gate alone must never authorize final COMPLETE.
            require_executor_turn_budget(time.monotonic()-probe_started)
        emit('chat_recent_timing_after',metrics())
    finally:
        try:request(client,'/chat/logout','POST',{}).close()
        except Exception:pass
    # Logout/metrics are part of elapsed probe time; check immediately before COMPLETE.
    require_executor_turn_budget(time.monotonic()-probe_started)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        reason=str(exc);emit('chat_probe_hold',{'reason':reason if re.fullmatch('[A-Z0-9_]{1,120}',reason) else type(exc).__name__})
        raise SystemExit(2)
