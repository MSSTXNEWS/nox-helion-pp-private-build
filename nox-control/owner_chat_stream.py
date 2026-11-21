"""Real owner SSE over the installed NOX model and existing guarded tools.

Installed by a source-pinned agent_loop patch. No model, scheduler, credentials
or persistence store is introduced here; chat_proxy retains its S03 postflight.
"""
from __future__ import annotations

import asyncio
import codecs
from contextlib import aclosing
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import stat
import time

import httpx
import owner_chat_evidence as _current


class StreamFailure(RuntimeError):
    pass


# Require one bounded, valid JSON envelope before native model POST. Never
# silently prune prior S03/persona turns to fit the limit; return an explicit HOLD.
MODEL_REQUEST_LIMIT=4000000

# Bound the cumulative browser/S03 result across multiple model/tool cycles.
# Individual upstream responses have their own 2M limit; the complete turn
# must obey the same ceiling before native postflight certifies it.
FINAL_RESPONSE_LIMIT=2000000


def _append_final_chunk(chunks, chunk, size):
    if type(chunk) is not str:
        raise StreamFailure('HOLD_MODEL_TOKEN_TYPE')
    size+=len(chunk)
    if size>FINAL_RESPONSE_LIMIT:
        raise StreamFailure('HOLD_MODEL_TOTAL_OUTPUT_SIZE')
    chunks.append(chunk)
    return size


EXECUTOR_STATUS=Path('/root/nox/status/agents_t856u.json')


def owner_request_query(user_text):
    """Keep current native facts/actions out of the legacy early-answer hook."""
    return (executor_status_query(user_text) or _current.relevant_query(user_text)
            or _current.media_status_query(user_text) is not None)


def executor_status_query(user_text):
    """Recognize current read-only executor questions, excluding action requests."""
    text=(user_text or '').casefold()
    if not re.search(r'(исполнител|агент)',text):return False
    if re.search(r'(включ|выключ|запуст|созда|назнач|добав|перенастр|увелич|уменьш|'
                 r'останов|нужно|надо|можешь|можно|будет|будут|завтра|вчера|раньше|'
                 r'было|были|работало|работали|прошл|истори)',text):return False
    count_question=bool(re.search(r'(сколько|количеств|число)',text))
    state_question=bool(re.search(r'(статус|состояни|занят|свобод|активн)',text))
    return count_question or state_question


def _executor_status_reply(user_text,path=None):
    """Answer current executor counts from one fresh native snapshot only."""
    if not executor_status_query(user_text):return None
    unknown=('Сейчас не могу подтвердить число и занятость исполнителей: '
             'свежий корректный статус диспетчера недоступен. '
             'NOX — отдельный координатор и чат; неподтверждённые цифры не привожу.')
    # Preserve the already-source-tested MODEL_UPDATE fence in this successor.
    # Source: c4e628c4ce81b75cc055e53a6e18d5388f1065e6.
    try:
        from owner_chat_ui import owner_maintenance_gate
        maintenance=owner_maintenance_gate()
    except Exception:
        return unknown
    if maintenance!='ABSENT':
        return ('Сейчас выполняется MODEL_UPDATE; статус исполнителей временно недоступен.'
                if maintenance=='PRESENT' else unknown)
    target=Path(path) if path is not None else EXECUTOR_STATUS
    try:
        # O_NOFOLLOW rejects symlinks; O_NONBLOCK prevents a FIFO from
        # wedging chat admission before fstat can reject nonregular files.
        fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as source:
            meta=os.fstat(source.fileno())
            # A fresh JSON file is not authoritative if other principals
            # can alter it. Require an owner-created status snapshot.
            if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                    or meta.st_mode & 0o022 or not 0<meta.st_size<=750000):
                return unknown
            age=time.time()-meta.st_mtime
            if not 0<=age<=45:return unknown
            raw=source.read(750001)
            if len(raw)!=meta.st_size or len(raw)>750000:return unknown
            # Detect in-place modifications even when the JSON stays valid.
            after=os.fstat(source.fileno())
            identity=lambda st:(st.st_dev,st.st_ino,st.st_mode,st.st_size,
                                st.st_mtime_ns,st.st_ctime_ns)
            if identity(after)!=identity(meta):return unknown
        # A rename after open must not certify an obsolete descriptor.
        if identity(os.stat(target,follow_symlinks=False))!=identity(meta):return unknown
        # JSON defaults accept duplicate keys and nonfinite constants.
        # Neither is trustworthy native status evidence.
        doc=json.loads(raw.decode('utf-8','strict'),
                       object_pairs_hook=_reject_duplicate_json_keys,
                       parse_constant=_reject_nonfinite_json_constant)
        if not isinstance(doc,dict):return unknown
        rows=doc.get('workers');n=doc.get('n')
        if type(n) is not int or not 1<=n<=64 or not isinstance(rows,list) or len(rows)!=n:return unknown
        ids=[];busy=0;active_task_ids=set()
        for row in rows:
            if not isinstance(row,dict):return unknown
            name=row.get('id');status=row.get('status');task=row.get('current_task')
            if not isinstance(name,str) or not re.fullmatch(r'nox-agent-\d{2,3}',name) or name in ids:return unknown
            if status=='busy':
                if not isinstance(task,dict) or not isinstance(task.get('id'),str) or not task['id']:return unknown
                # Two busy workers claiming the same TaskID is not a trustworthy
                # lease/registry snapshot. Do not report duplicate work as real.
                if task['id'] in active_task_ids:return unknown
                active_task_ids.add(task['id'])
                busy+=1
            elif status=='idle':
                if task is not None:return unknown
            else:return unknown
            ids.append(name)
        if owner_maintenance_gate()!='ABSENT':return unknown
        observed=datetime.fromtimestamp(meta.st_mtime,timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        # This file describes logical scheduler slots, not authenticated
        # native process identities. Never turn its freshness alone into a
        # claim about live PIDs, GPU execution or the owner lease.
        return (f'По файлу диспетчера настроено {n} логических исполнителей: '
                f'по записи занято {busy}, свободно {n-busy}. '
                f'NOX — отдельный координатор и чат (1). Схема: {n} исполнителей + NOX.\n'
                f'Логические слоты: {", ".join(ids)}.\n'
                f'Источник: файл статуса диспетчера, {observed}. '
                'Это не подтверждение живых PID/start_ticks, owner lease/CAS, '
                'работы GPU или числа физических native workers.')
    except (OSError,ValueError,TypeError,OverflowError):
        return unknown


async def _bounded_sse_lines(response):
    """Bound partial SSE fields before a newline; httpx.aiter_lines() does not.

    Preserve CR, LF, CRLF (including split CRLF) and UTF-8 chunk boundaries.
    No buffering of untrusted unterminated model output beyond 300k chars.
    """
    pending=''
    after_cr=False
    # Un-sized chunks preserve immediate first-token delivery. Fixed-size
    # HTTPX text chunking can wait for 8 KiB and stall a live SSE response.
    # HTTPX aiter_text() uses replacement decoding for malformed UTF-8:
    # that silently turns corrupt model bytes into apparently valid tokens.
    # Preserve all split-codepoint boundaries, but never certify damaged text.
    decoder=codecs.getincrementaldecoder('utf-8')('strict')
    async for raw in response.aiter_bytes():
        try:
            chunk=decoder.decode(raw)
        except UnicodeDecodeError:
            raise StreamFailure('HOLD_MODEL_SSE_INVALID') from None
        for offset in range(0,len(chunk),8192):
            for part in re.split(r'(\r\n|\r|\n)',chunk[offset:offset+8192]):
                if part in ('\r\n','\r','\n'):
                    if part=='\n' and after_cr:
                        after_cr=False
                        continue
                    yield pending
                    pending=''
                    after_cr=(part=='\r')
                elif part:
                    after_cr=False
                    pending+=part
                    if len(pending)>300000:
                        raise StreamFailure('HOLD_MODEL_SSE_FRAME')
    try:
        decoder.decode(b'',final=True)
    except UnicodeDecodeError:
        raise StreamFailure('HOLD_MODEL_SSE_INVALID') from None
    if pending:
        yield pending


def _reject_duplicate_json_keys(pairs):
    """Reject ambiguous model/tool JSON before dispatch or S03 certification."""
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def _reject_nonfinite_json_constant(value):
    """JSON does not permit NaN or Infinity in SSE or tool arguments."""
    raise ValueError('non-finite JSON constant')


def _reject_lone_surrogates(value):
    """Reject non-scalar Unicode before publishing an SSE token or tool call."""
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError('unpaired UTF-16 surrogate')


async def _model_events(client, url, payload):
    """Forward content immediately; assemble function-call arguments privately."""
    # The native OneHost request is authoritative about its selected model.
    # Never substitute a different model for an explicitly selected one.
    request=dict(payload,stream=True,cache_prompt=True)
    if 'model' in request:
        model=request['model']
        if type(model) is not str or not 0<len(model.strip())<=200:
            raise StreamFailure('HOLD_MODEL_IDENTITY')
    else:
        # Preserve the pre-existing alias for legacy callers without a model.
        request['model']='maya'
    # The original authenticated S03 context may be arbitrarily long and each
    # tool cycle appends messages. Reject an oversized aggregate POST before
    # HTTPX serializes it or a native model sees partial/lost conversation.
    # Do not truncate context, tool observations, or provenance.
    try:
        request_wire=json.dumps(request,ensure_ascii=False,allow_nan=False,
                                separators=(',',':')).encode('utf-8','strict')
    except (TypeError,ValueError,UnicodeError,OverflowError,RecursionError):
        raise StreamFailure('HOLD_MODEL_REQUEST_INVALID') from None
    if len(request_wire)>MODEL_REQUEST_LIMIT:
        raise StreamFailure('HOLD_MODEL_REQUEST_SIZE')
    del request_wire
    text=[];calls={};finished=None;complete=False;size=0
    async with client.stream('POST',url,json=request,timeout=180.0) as response:
        if response.status_code!=200:
            raise StreamFailure('HOLD_MODEL_HTTP')
        # A data: line is a field, not an event; dispatch only on a blank line.
        # Preserve valid multi-line JSON without allowing unbounded frames.
        parts=[]
        frame_size=0
        record_size=0
        frame_lines=0
        first_line=True
        async for line in _bounded_sse_lines(response):
            # WHATWG SSE decoding ignores one leading UTF-8 BOM, and only
            # at the start of the stream. Do not erase later payload bytes.
            if first_line:
                first_line=False
                if line.startswith('\ufeff'):
                    line=line[1:]
            if line:
                # A legal stream may send keepalives, but an unbounded single
                # record of comments/ids can otherwise starve chat indefinitely.
                frame_lines+=1
                # Comments and id/retry/event metadata also consume memory and
                # parsing time. Cap aggregate record bytes, not only data:.
                record_size+=len(line)+1
                if frame_lines>1024 or len(line)>300000 or record_size>300000:
                    raise StreamFailure('HOLD_MODEL_SSE_FRAME')
            else:
                # Each empty line ends one SSE record (including keepalives).
                frame_lines=0
                record_size=0
            if line=='':
                if not parts:
                    continue
                wire='\n'.join(parts).strip()
                parts=[]
                frame_size=0
            elif line.startswith(':'):
                continue
            elif line.startswith('event:') or line=='event':
                if line!='event' and line[6:].strip()!='message':
                    raise StreamFailure('HOLD_MODEL_SSE_EVENT')
                continue
            elif line.startswith('id:') or line=='id':
                if len(line)>256 or '\x00' in line:
                    raise StreamFailure('HOLD_MODEL_SSE_FRAME')
                continue
            elif line.startswith('retry:') or line=='retry':
                # A provider may supply SSE reconnection advice. This adapter
                # never reconnects model POSTs (no risk of duplicate tool use).
                # Ignore the bounded metadata while retaining event framing.
                if len(line)>256:
                    raise StreamFailure('HOLD_MODEL_SSE_FRAME')
                continue
            elif line.startswith('data:') or line=='data':
                # WHATWG: a field without ':' has an empty value. A bare
                # `data` is still a data field, not an unknown SSE command.
                value=line[5:] if line!='data' else ''
                if value.startswith(' '):
                    value=value[1:]
                frame_size+=len(value)+1
                if frame_size>300000:
                    raise StreamFailure('HOLD_MODEL_SSE_SIZE')
                parts.append(value)
                continue
            else:
                raise StreamFailure('HOLD_MODEL_SSE_FRAME')
            if wire=='[DONE]':
                complete=True
                break
            if len(wire)>300000:
                raise StreamFailure('HOLD_MODEL_SSE_SIZE')
            try:
                doc=json.loads(wire,object_pairs_hook=_reject_duplicate_json_keys,
                               parse_constant=_reject_nonfinite_json_constant)
                # Any explicit error field signals provider failure, even when its
                # value is {}, [], false or null. Reject before showing tokens
                # or certifying a successful S03 terminal.
                if not isinstance(doc,dict) or 'error' in doc:
                    raise ValueError('error')
                choices=doc.get('choices')
                if choices==[] and isinstance(doc.get('usage'),dict):
                    continue
                if not isinstance(choices,list) or len(choices)!=1:
                    raise ValueError('choices')
                choice=choices[0]
                delta=choice.get('delta')
                if delta is None:delta={}
                if not isinstance(delta,dict):
                    raise ValueError('delta')
                # A valid terminal choice closes the model's content/tool delta.
                # Usage-only epilogues remain legal, but no content after finish
                # may be shown to the browser or certified by the S03 postflight.
                already_finished=finished is not None
                reason=choice.get('finish_reason')
                if reason is not None:
                    if reason not in ('stop','tool_calls'):
                        raise StreamFailure('HOLD_MODEL_INCOMPLETE')
                    finished=reason
                part=delta.get('content')
                if part is not None and not isinstance(part,str):
                    raise ValueError('content')
                if part is not None:_reject_lone_surrogates(part)
                fragments=delta.get('tool_calls')
                if fragments is None:fragments=[]
                if not isinstance(fragments,list):
                    raise ValueError('calls')
                if already_finished and (reason is not None or part or fragments):
                    raise StreamFailure('HOLD_MODEL_POST_TERMINAL_DELTA')
                if part:
                    size+=len(part)
                    if size>2000000:
                        raise StreamFailure('HOLD_MODEL_OUTPUT_SIZE')
                    text.append(part)
                    yield 'token',part
                for fragment in fragments:
                    index=fragment.get('index')
                    if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<8:
                        raise ValueError('call index')
                    call=calls.setdefault(index,{'id':'','type':'function',
                                                'function':{'name':'','arguments':''}})
                    if fragment.get('type','function')!='function':
                        raise ValueError('call type')
                    for field in ('id',):
                        value=fragment.get(field)
                        if value is not None:
                            if not isinstance(value,str):raise ValueError(field)
                            _reject_lone_surrogates(value)
                            call[field]+=value
                            # Model-supplied SSE identifiers are untrusted. A long ID
                            # must never reach the native tool dispatcher or S03.
                            if len(call[field])>160:
                                raise StreamFailure('HOLD_TOOL_CALL_ID_SIZE')
                    function=fragment.get('function')
                    # Only missing/null is a legal id-only continuation. Reject
                    # falsey non-objects instead of silently treating them as {}.
                    if function is None:function={}
                    if not isinstance(function,dict):raise ValueError('function')
                    for field in ('name','arguments'):
                        value=function.get(field)
                        if value is not None:
                            if not isinstance(value,str):raise ValueError(field)
                            _reject_lone_surrogates(value)
                            call['function'][field]+=value
                    if len(call['function']['arguments'])>100000 or len(call['function']['name'])>200:
                        raise StreamFailure('HOLD_TOOL_CALL_SIZE')
            except StreamFailure:
                raise
            except (AttributeError,TypeError,ValueError):
                raise StreamFailure('HOLD_MODEL_SSE_INVALID') from None
    if not complete or finished not in ('stop','tool_calls'):
        raise StreamFailure('HOLD_MODEL_STREAM_INCOMPLETE')
    if bool(calls)!=(finished=='tool_calls'):
        raise StreamFailure('HOLD_TOOL_CALL_TERMINAL')
    message={'role':'assistant','content':''.join(text)}
    if calls:
        ordered=[calls[index] for index in sorted(calls)]
        if any(not call['id'] or not call['function']['name'] for call in ordered):
            raise StreamFailure('HOLD_TOOL_CALL_ID')
        if len({call['id'] for call in ordered})!=len(ordered):
            raise StreamFailure('HOLD_TOOL_CALL_ID')
        message['tool_calls']=ordered
    elif not message['content'].strip():
        raise StreamFailure('HOLD_MODEL_EMPTY')
    yield 'message',message


def _native_json_value(value):
    """Reject Python-to-JSON shape changes before passing tool arguments.

    json.dumps accepts integer keys and tuples by silently converting them to
    JSON strings/arrays. A pre-parsed native tool call must mean exactly what
    was supplied rather than dispatching with an invented argument shape.
    """
    if type(value) is dict:
        for key,item in value.items():
            if type(key) is not str:
                raise ValueError('non-string tool argument key')
            _native_json_value(item)
    elif type(value) is list:
        for item in value:
            _native_json_value(item)
    elif value is None or type(value) in (str,int,float,bool):
        return
    else:
        raise ValueError('non-JSON tool argument value')


def _normal_calls(rows,step):
    if not isinstance(rows,list) or len(rows)>8:
        raise StreamFailure('HOLD_TOOL_CALL_COUNT')
    result=[]
    seen_ids=set()
    for index,row in enumerate(rows):
        if not isinstance(row,dict):
            raise StreamFailure('HOLD_TOOL_CALL_SHAPE')
        name=row.get('name')
        # Heuristic/direct calls never pass through the streamed model parser.
        # Reject malformed tool identities at their shared native boundary.
        if (type(name) is not str or not 1<=len(name)<=200 or
                any(ord(char)<32 or 127<=ord(char)<=159 or
                    0xD800<=ord(char)<=0xDFFF for char in name)):
            raise StreamFailure('HOLD_TOOL_CALL_SHAPE')
        args=row.get('arguments')
        # Missing/null or a blank native argument string means no arguments.
        # Falsey non-objects ([], false, 0) must never become {} and dispatch.
        if args is None or (isinstance(args,str) and not args):args={}
        if isinstance(args,str):
            try:args=json.loads(args,object_pairs_hook=_reject_duplicate_json_keys,
                                parse_constant=_reject_nonfinite_json_constant)
            except ValueError:raise StreamFailure('HOLD_TOOL_ARGUMENTS') from None
        if not isinstance(args,dict):raise StreamFailure('HOLD_TOOL_ARGUMENTS')
        # JSON string arguments were parsed strictly above, but pre-parsed
        # heuristic/deterministic dicts and nested JSON escapes may still
        # contain NaN, Infinity or lone UTF-16 surrogates. Validate the exact
        # object before a native tool can see it.
        try:
            _native_json_value(args)
            encoded=json.dumps(args,ensure_ascii=False,allow_nan=False).encode('utf-8','strict')
            if len(encoded)>100000:raise ValueError('oversized tool arguments')
        except (UnicodeError,TypeError,ValueError,RecursionError):
            raise StreamFailure('HOLD_TOOL_ARGUMENTS') from None
        # Native parser / deterministic routes share the same bounded ID rule.
        call_id=row.get('id')
        if call_id is not None and (type(call_id) is not str or
                not 1<=len(call_id)<=160 or
                any(ord(char)<32 or 127<=ord(char)<=159 or
                    0xD800<=ord(char)<=0xDFFF for char in call_id)):
            raise StreamFailure('HOLD_TOOL_CALL_ID_SIZE')
        effective_id=call_id if call_id is not None else f'owner_call_{step}_{index}'
        # Duplicate native IDs can double-execute a side effect yet give S03
        # two different results under one tool_call_id. Include generated IDs.
        if effective_id in seen_ids:
            raise StreamFailure('HOLD_TOOL_CALL_ID')
        seen_ids.add(effective_id)
        result.append({'id':effective_id,'name':name,'arguments':args})
    return result


def _refuse_multi_admin_batch(calls):
    """A model/tool batch must not silently execute one admin action and drop the rest."""
    if len(calls)>1 and any(call['name']=='run_admin' for call in calls):
        raise StreamFailure('HOLD_DIRECT_ADMIN_MULTIPLE_ACTIONS')


def _assistant_tools(calls,content=''):
    return {'role':'assistant','content':content,'tool_calls':[
        {'id':call['id'],'type':'function','function':{
            'name':call['name'],'arguments':json.dumps(call['arguments'],ensure_ascii=False)}}
        for call in calls]}


async def _run(native,url,payload,user_text):
    executor_reply=(await asyncio.to_thread(_executor_status_reply,user_text)
                    if executor_status_query(user_text) else None)
    if executor_reply is not None:
        yield 'token',executor_reply
        return
    # Do not silently execute only the first action from a multi-action
    # administrator turn. Gate before S03 augmentation and model/route admission.
    calls=native['_direct_admin_calls'](user_text or '') or []
    if len(calls)>1:
        raise StreamFailure('HOLD_DIRECT_ADMIN_MULTIPLE_ACTIONS')
    direct=bool(calls)
    turn={}
    intent=_current.explicit_media_request(user_text)
    status_id=_current.media_status_query(user_text)
    if intent or status_id:
        name='owner_queue_media_v1' if intent else 'owner_media_job_v1'
        arguments={'kind':intent['kind']} if intent else {'job_id':status_id}
        rec=await asyncio.to_thread(_current.dispatch,name,arguments,user_text,turn)
        # The direct media fast path bypasses the normal tool loop. Demand
        # the same truthful, typed outcome before audit/S03/browser success.
        # This route has no confirmation continuation, so fail closed on one.
        if (not isinstance(rec,dict) or type(rec.get('ok')) is not bool
                or type(rec.get('text')) is not str or not rec['text'].strip()
                or len(rec['text'])>2000000
                or ('needs_confirmation' in rec and rec['needs_confirmation'] is not False)
                or ('error' in rec and rec.get('ok') is True)):
            raise StreamFailure('HOLD_MEDIA_RESULT_FIDELITY')
        await asyncio.to_thread(native['audit'],'tool_step',name=name,step=1,ok=rec['ok'])
        if not rec['ok']:
            # An unverified media enqueue may be visible to the user, but it
            # must not become a successful terminal/S03 postflight receipt.
            yield 'token',rec['text']
            raise StreamFailure('HOLD_MEDIA_RESULT_UNCONFIRMED')
        yield 'token',rec['text']
        return
    if _current.download_status_query(user_text):
        yield 'token',await asyncio.to_thread(_current.inventory_reply)
        return
    # Existing S03 payload also belongs to the request-bound postflight writer.
    # A shallow dict copy shares nested content and lets the evidence augmenter
    # corrupt that stored dialogue before the model has answered.
    try:
        source_messages=payload.get('messages')
        if source_messages is None:source_messages=[]
        if not isinstance(source_messages,list) or any(
                not isinstance(message,dict) for message in source_messages):
            raise ValueError('invalid message history')
        history_wire=json.dumps(source_messages,ensure_ascii=False,
                                allow_nan=False).encode('utf-8','strict')
        messages=json.loads(history_wire)
    except (TypeError,ValueError,UnicodeError,OverflowError,RecursionError):
        raise StreamFailure('HOLD_MODEL_CONTEXT_FIDELITY') from None
    if _current.relevant_query(user_text):
        # Evidence may annotate the leading system message, but it must not
        # silently drop, reorder, or rewrite any persisted dialogue turn.
        # Compare against the detached pre-augmentation wire: an augmenter
        # could mutate the messages list in place before returning it.
        augmented=await asyncio.to_thread(_current.augment_messages,messages,user_text)
        try:
            original=json.loads(history_wire)
            had_system=bool(original) and original[0].get('role')=='system'
            expected_len=len(original)+(0 if had_system else 1)
            if type(augmented) is not list or len(augmented)!=expected_len:
                raise ValueError('evidence changed history length')
            system=augmented[0]
            if type(system) is not dict or system.get('role')!='system':
                raise ValueError('evidence changed system role')
            expected_tail=original[1:] if had_system else original
            canonical=lambda value:json.dumps(
                value,sort_keys=True,ensure_ascii=False,allow_nan=False,
                separators=(',',':')).encode('utf-8','strict')
            if canonical(augmented[1:])!=canonical(expected_tail):
                raise ValueError('evidence changed stored turns')
            if had_system:
                initial=original[0]
                unchanged=dict(system,content=initial.get('content'))
                if canonical(unchanged)!=canonical(initial):
                    raise ValueError('evidence changed system metadata')
                # Existing multimodal/structured system content may be
                # enriched in place; only plain text has a stable prefix.
                if type(initial.get('content')) is str:
                    prefix=initial['content']+'\n\n'
                    if (type(system.get('content')) is not str
                            or not system['content'].startswith(prefix)):
                        raise ValueError('evidence replaced system content')
            elif type(system.get('content')) is not str or not system['content'].strip():
                raise ValueError('evidence missing system context')
        except (TypeError,ValueError,UnicodeError,OverflowError,RecursionError):
            raise StreamFailure('HOLD_MODEL_CONTEXT_FIDELITY') from None
        messages=augmented
    native_tools=list(native['TOOLS'])
    if _current.relevant_query(user_text):
        if any((row.get('function') or {}).get('name') in _current.NAMES for row in native_tools):
            raise StreamFailure('HOLD_OWNER_TOOL_NAME_COLLISION')
        native_tools+=_current.tools()
    # The pool's cache/key preparation must see the exact evidence-augmented
    # context that the model POST will receive. Keep the caller/S03 payload
    # untouched; otherwise a cache decision can be made for a different turn.
    req=dict(payload,messages=messages)
    req.pop('_agent_final',None)
    req.update(tools=native_tools,tool_choice='auto',stream=True,cache_prompt=True)
    # Native Qwen3.5 fixture verified this mode: visible tokens start directly.
    # Explicit callers may opt into deliberation; ordinary chat defaults fast.
    template=dict(req.get('chat_template_kwargs') or {})
    template.setdefault('enable_thinking',False)
    req['chat_template_kwargs']=template
    if native.get('_POOL'):
        # The pool may optimize caching, but cannot silently substitute the
        # request's explicitly selected model before the actual OneHost POST.
        # Missing model remains a legacy server/pool selection, unchanged.
        explicit_model='model' in req
        selected=req['model'] if explicit_model else None
        # Pool caching may not remove or rewrite any S03/persona/chat turn.
        # Snapshot before calling the optimizer: it may mutate its input in
        # place. Give it an isolated JSON copy, never the caller's live list.
        try:
            context_wire=json.dumps(req['messages'],sort_keys=True,
                                    ensure_ascii=False,allow_nan=False,
                                    separators=(',',':')).encode('utf-8','strict')
            # Cache/pool preparation must not silently disable tools or
            # turn deliberate fast-response chat into unrequested thinking.
            # A detached wire snapshot detects in-place nested rewrites too.
            control_wire=json.dumps({
                'tool_choice':req['tool_choice'],
                'chat_template_kwargs':req['chat_template_kwargs']},
                sort_keys=True,ensure_ascii=False,allow_nan=False,
                separators=(',',':')).encode('utf-8','strict')
            # The cache optimizer must not silently remove or rewrite model
            # tool schemas. Clone them before pool admission: a shallow list
            # copy shares nested native definitions and hides in-place edits.
            tools_wire=json.dumps(native_tools,sort_keys=True,
                                  ensure_ascii=False,allow_nan=False,
                                  separators=(',',':')).encode('utf-8','strict')
        except (TypeError,ValueError,UnicodeError,OverflowError,RecursionError):
            raise StreamFailure('HOLD_MODEL_CONTEXT_FIDELITY') from None
        pool_input=dict(req,messages=json.loads(context_wire),
                        tools=json.loads(tools_wire),
                        chat_template_kwargs=json.loads(control_wire)['chat_template_kwargs'])
        prepared=native['prepare_payload'](pool_input,cache=True)
        if not isinstance(prepared,dict):
            raise StreamFailure('HOLD_MODEL_IDENTITY')
        try:
            after_wire=json.dumps(prepared['messages'],sort_keys=True,
                                  ensure_ascii=False,allow_nan=False,
                                  separators=(',',':')).encode('utf-8','strict')
            after_control_wire=json.dumps({
                'tool_choice':prepared.get('tool_choice'),
                'chat_template_kwargs':prepared.get('chat_template_kwargs')},
                sort_keys=True,ensure_ascii=False,allow_nan=False,
                separators=(',',':')).encode('utf-8','strict')
            after_tools_wire=json.dumps(prepared.get('tools'),sort_keys=True,
                                        ensure_ascii=False,allow_nan=False,
                                        separators=(',',':')).encode('utf-8','strict')
        except (KeyError,TypeError,ValueError,UnicodeError,OverflowError,RecursionError):
            raise StreamFailure('HOLD_MODEL_CONTEXT_FIDELITY') from None
        if after_wire!=context_wire:
            raise StreamFailure('HOLD_MODEL_CONTEXT_FIDELITY')
        if after_control_wire!=control_wire:
            raise StreamFailure('HOLD_MODEL_CONTROL_FIDELITY')
        if after_tools_wire!=tools_wire:
            raise StreamFailure('HOLD_MODEL_TOOL_SCHEMA_FIDELITY')
        if explicit_model and (type(selected) is not str or
                               not 0<len(selected.strip())<=200 or
                               type(prepared.get('model')) is not str or
                               prepared['model']!=selected):
            raise StreamFailure('HOLD_MODEL_IDENTITY')
        req=prepared
        req['tools']=json.loads(tools_wire)
    steps=0
    # Resolve existing deterministic routes before any model text is shown.
    # Never reinterpret already-streamed prose as an executable command.
    if not calls and native.get('_POOL'):
        deterministic=native['try_deterministic'](user_text or '')
        if deterministic and deterministic.get('name')=='clock' and deterministic.get('text'):
            yield 'token',str(deterministic['text'])
            return
        if deterministic and deterministic.get('tool'):
            # Preserve raw provider arguments for _normal_calls validation.
            # Falsey non-dicts must HOLD, never be reinterpreted as {}.
            calls=[{'name':deterministic['tool'],
                    'arguments':deterministic.get('arguments')}]
            direct=True
    if not calls:
        calls=native['heuristic_tools'](user_text or '') or []
    calls=_normal_calls(calls,steps)
    _refuse_multi_admin_batch(calls)
    if calls:messages.append(_assistant_tools(calls))
    async with httpx.AsyncClient(timeout=180.0,trust_env=False) as client:
        while True:
            if calls:
                for call in calls:
                    if steps>=int(native.get('MAX_STEPS',8)):
                        raise StreamFailure('HOLD_TOOL_STEP_LIMIT')
                    steps+=1
                    rec=await asyncio.to_thread(_current.dispatch,call['name'],call['arguments'],user_text,turn)
                    if rec is None:
                        rec=await asyncio.to_thread(native['dispatch'],call['name'],call['arguments'])
                    if not isinstance(rec,dict):raise StreamFailure('HOLD_TOOL_RESULT')
                    # A contradictory provider envelope cannot certify a tool
                    # success even if the error value is falsey or null.
                    if rec.get('ok') is True and 'error' in rec:
                        raise StreamFailure('HOLD_TOOL_RESULT_ERROR_CONFLICT')
                    # A direct command result is the final user-visible
                    # outcome, not a model observation. Missing "ok" is NOT
                    # evidence of success and must never certify S03/DONE.
                    final_command=(direct or (call['name']=='run_admin'
                        and call['arguments'].get('action') in native['DIRECT_ADMIN']))
                    if (('ok' not in rec and final_command)
                            or ('ok' in rec and type(rec['ok']) is not bool)):
                        raise StreamFailure('HOLD_TOOL_RESULT_OK')
                    if 'needs_confirmation' in rec and type(rec['needs_confirmation']) is not bool:
                        raise StreamFailure('HOLD_TOOL_RESULT_CONFIRMATION')
                    # Validate the entire tool observation before recording
                    # an audit success. An invalid/oversized text result must
                    # not generate a green tool_step when chat and S03 HOLD.
                    text=rec['text'] if 'text' in rec else ''
                    if not isinstance(text,str):raise StreamFailure('HOLD_TOOL_RESULT')
                    if rec.get('ok') is False and not rec.get('needs_confirmation'):
                        text='Инструмент не подтвердил выполнение действия. '+text
                    if rec.get('needs_confirmation'):
                        text+=native['confirm_marker'](rec)
                        if not text.strip():raise StreamFailure('HOLD_TOOL_CONFIRMATION')
                    if final_command and not text.strip():
                        raise StreamFailure('HOLD_TOOL_EMPTY')
                    # Every route, including direct commands and pending owner
                    # confirmations, must fit the same bounded chat/S03 result.
                    # No successful audit or final ACK may certify an oversized
                    # tool observation that can exhaust scarce host memory.
                    if len(text)>2000000:
                        raise StreamFailure('HOLD_TOOL_RESULT_FULL_CONTEXT')
                    await asyncio.to_thread(native['audit'],'tool_step',name=call['name'],
                                            step=steps,
                                            # A confirmation request is NOT a completed
                                            # tool action even if the provider's `ok`
                                            # field is true. Keep audit truth separate
                                            # from user-visible confirmation text.
                                            ok=(rec.get('ok') is True and
                                                rec.get('needs_confirmation') is not True))
                    if rec.get('needs_confirmation'):
                        yield 'token',text
                        return
                    if final_command:
                        if rec['ok'] is not True:
                            # Show the actual failure without claiming [DONE]
                            # or making the S03 postflight mark it successful.
                            yield 'token',text
                            raise StreamFailure('HOLD_TOOL_RESULT_UNCONFIRMED')
                        yield 'token',text
                        return
                    messages.append({'role':'tool','tool_call_id':call['id'],
                                     'name':call['name'],'content':text})
            calls=[]
            model_request=dict(req,messages=messages,cache_prompt=True)
            if steps>=int(native.get('MAX_STEPS',8)):
                model_request.pop('tools',None)
                model_request['tool_choice']='none'
            message=None
            async with aclosing(_model_events(client,url,model_request)) as model_stream:
                async for kind,value in model_stream:
                    if kind=='token':
                        yield kind,value
                    elif kind=='message':message=value
            if message is None:raise StreamFailure('HOLD_MODEL_EMPTY')
            if not message.get('tool_calls'):
                return
            # Function-call arguments stayed private until a complete tool_calls
            # terminal. Keep exact IDs for the original native dispatch contract.
            own=[];legacy=[]
            for row in message['tool_calls']:
                function=row['function']
                if function['name'] in _current.NAMES:
                    own.append({'id':row['id'],'name':function['name'],'arguments':function['arguments']})
                else:legacy.append(row)
            parsed=native['parse_tool_calls'](dict(message,tool_calls=legacy),'') if legacy else []
            calls=_normal_calls(own+parsed,steps)
            if not calls:raise StreamFailure('HOLD_TOOL_PARSE')
            by_id={call['id']:call for call in calls}
            if len(by_id)!=len(calls) or set(by_id)!={call['id'] for call in message['tool_calls']}:
                raise StreamFailure('HOLD_TOOL_CALL_ID')
            # The native parser may normalize JSON formatting, but must not
            # rewrite a model-requested tool name or argument value while
            # preserving the original call ID. Check the exact model envelope
            # before dispatch, before admin admission, and before S03 postflight.
            for row in message['tool_calls']:
                call=by_id[row['id']]
                function=row['function']
                try:
                    expected_args=function['arguments']
                    if expected_args=='':
                        expected_args={}
                    else:
                        expected_args=json.loads(
                            expected_args,object_pairs_hook=_reject_duplicate_json_keys,
                            parse_constant=_reject_nonfinite_json_constant)
                    # Python equality treats True == 1 and 1 == 1.0. A
                    # native parser must not change JSON scalar types while
                    # keeping the same call ID: this changes tool semantics.
                    # Canonical JSON preserves scalar types but ignores harmless
                    # object-key ordering and JSON escape formatting.
                    expected_wire=json.dumps(expected_args,sort_keys=True,
                                             ensure_ascii=False,allow_nan=False,
                                             separators=(',',':'))
                    actual_wire=json.dumps(call['arguments'],sort_keys=True,
                                           ensure_ascii=False,allow_nan=False,
                                           separators=(',',':'))
                    if (call['name']!=function['name']
                            or not isinstance(expected_args,dict)
                            or actual_wire!=expected_wire):
                        raise ValueError('parser changed tool payload')
                except (TypeError,ValueError,KeyError):
                    raise StreamFailure('HOLD_TOOL_CALL_ARGUMENT_FIDELITY') from None
            calls=[by_id[row['id']] for row in message['tool_calls']]
            # Inspect the *original* model batch: pool deduplication must not
            # hide a second action and accidentally authorize run_admin.
            _refuse_multi_admin_batch(calls)
            if native.get('_POOL'):
                # The parsed model envelope was verified above, but the pool
                # may edit a call in place while deduplicating. Record a
                # detached semantic fingerprint before invoking that hook.
                before_ids=[call['id'] for call in calls]
                before={
                    call['id']:(call['name'],json.dumps(
                        call['arguments'],sort_keys=True,ensure_ascii=False,
                        allow_nan=False))
                    for call in calls}
                reduced=native['dedup_calls'](calls)
                if not isinstance(reduced,list) or not reduced:
                    raise StreamFailure('HOLD_TOOL_POOL_FIDELITY')
                seen=set()
                selected=[]
                for call in reduced:
                    try:
                        call_id=call['id']
                        if (type(call_id) is not str or call_id in seen or
                                call_id not in before):
                            raise ValueError('new/duplicate call ID')
                        evidence=(call['name'],json.dumps(
                            call['arguments'],sort_keys=True,
                            ensure_ascii=False,allow_nan=False))
                        if evidence!=before[call_id]:
                            raise ValueError('pool changed tool call')
                    except (TypeError,KeyError,ValueError,OverflowError):
                        raise StreamFailure('HOLD_TOOL_POOL_FIDELITY') from None
                    seen.add(call_id)
                    selected.append(call_id)
                if selected!=[call_id for call_id in before_ids if call_id in seen]:
                    raise StreamFailure('HOLD_TOOL_POOL_FIDELITY')
                calls=reduced
            if not calls:raise StreamFailure('HOLD_TOOL_PARSE')
            _refuse_multi_admin_batch(calls)
            messages.append(_assistant_tools(calls,message['content']))


def install(native):
    """Replace the owner completion seam; original confirmation API stays intact."""
    async def owner_completion(url,payload,user_text,stream):
        from fastapi.responses import JSONResponse,StreamingResponse
        payload.pop('_agent_final',None)

        async def generate():
            answer=[]
            answer_chars=0
            try:
                async with aclosing(_run(native,url,payload,user_text)) as run:
                    async for kind,text in run:
                        if kind=='token' and text:
                            answer_chars=_append_final_chunk(answer,text,answer_chars)
                            yield native['_sse'](text)
                final=''.join(answer)
                if not final.strip():raise StreamFailure('HOLD_MODEL_EMPTY')
                # S03 postflight reads this only after normal exhaustion. Set it
                # before terminal DONE, never in a disconnect/error finally.
                payload['_agent_final']=final
                yield native['_sse']('',finish='stop')
                yield 'data: [DONE]\n\n'
            except (asyncio.CancelledError, GeneratorExit):
                # A client may close the SSE stream after the finish chunk but
                # before [DONE]. Never leave a postflight-ready answer behind
                # for a response the browser did not fully consume.
                payload.pop('_agent_final',None)
                raise
            except Exception as error:
                payload.pop('_agent_final',None)
                code=str(error) if isinstance(error,StreamFailure) else 'HOLD_OWNER_STREAM_RUNTIME'
                yield 'data: '+json.dumps({'error':{'code':code}})+'\n\n'

        if stream:
            return StreamingResponse(generate(),media_type='text/event-stream',headers={
                'Cache-Control':'no-cache, no-store','X-Accel-Buffering':'no'})
        try:
            answer=[]
            answer_chars=0
            async with aclosing(_run(native,url,payload,user_text)) as run:
                async for kind,text in run:
                    if kind=='token' and text:
                        answer_chars=_append_final_chunk(answer,text,answer_chars)
            final=''.join(answer)
            if not final.strip():raise StreamFailure('HOLD_MODEL_EMPTY')
            payload['_agent_final']=final
            return JSONResponse(native['_final_json'](final))
        except Exception as error:
            payload.pop('_agent_final',None)
            # Non-stream clients must receive the same verified HOLD code as
            # SSE clients; unknown failures still expose no internal details.
            code=str(error) if isinstance(error,StreamFailure) else 'HOLD_OWNER_STREAM_RUNTIME'
            return JSONResponse({'error':{'code':code}},status_code=502)

    native['owner_completion']=owner_completion
