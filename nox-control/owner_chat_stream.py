"""Real owner SSE over the installed NOX model and existing guarded tools.

Installed by a source-pinned agent_loop patch. No model, scheduler, credentials
or persistence store is introduced here; chat_proxy retains its S03 postflight.
"""
from __future__ import annotations

import asyncio
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
            if not stat.S_ISREG(meta.st_mode) or not 0<meta.st_size<=750000:return unknown
            age=time.time()-meta.st_mtime
            if not 0<=age<=45:return unknown
            raw=source.read(750001)
            if len(raw)>750000:return unknown
        doc=json.loads(raw)
        if not isinstance(doc,dict):return unknown
        rows=doc.get('workers');n=doc.get('n')
        if type(n) is not int or not 1<=n<=64 or not isinstance(rows,list) or len(rows)!=n:return unknown
        ids=[];busy=0
        for row in rows:
            if not isinstance(row,dict):return unknown
            name=row.get('id');status=row.get('status');task=row.get('current_task')
            if not isinstance(name,str) or not re.fullmatch(r'nox-agent-\d{2,3}',name) or name in ids:return unknown
            if status=='busy':
                if not isinstance(task,dict) or not isinstance(task.get('id'),str) or not task['id']:return unknown
                busy+=1
            elif status=='idle':
                if task is not None:return unknown
            else:return unknown
            ids.append(name)
        if owner_maintenance_gate()!='ABSENT':return unknown
        observed=datetime.fromtimestamp(meta.st_mtime,timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        return (f'Сейчас у диспетчера настроено {n} исполнителей: занято {busy}, свободно {n-busy}. '
                f'NOX — отдельный координатор и чат (1). Схема: {n} исполнителей + NOX.\n'
                f'Исполнители: {", ".join(ids)}.\nИсточник: свежий статус диспетчера, {observed}.')
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
    async for chunk in response.aiter_text():
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


async def _model_events(client, url, payload):
    """Forward content immediately; assemble function-call arguments privately."""
    request=dict(payload,model='maya',stream=True,cache_prompt=True)
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
                doc=json.loads(wire,object_pairs_hook=_reject_duplicate_json_keys)
                if not isinstance(doc,dict) or doc.get('error'):
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


def _normal_calls(rows,step):
    if not isinstance(rows,list) or len(rows)>8:
        raise StreamFailure('HOLD_TOOL_CALL_COUNT')
    result=[]
    for index,row in enumerate(rows):
        if not isinstance(row,dict) or not isinstance(row.get('name'),str):
            raise StreamFailure('HOLD_TOOL_CALL_SHAPE')
        args=row.get('arguments')
        # Missing/null or a blank native argument string means no arguments.
        # Falsey non-objects ([], false, 0) must never become {} and dispatch.
        if args is None or (isinstance(args,str) and not args):args={}
        if isinstance(args,str):
            try:args=json.loads(args,object_pairs_hook=_reject_duplicate_json_keys)
            except ValueError:raise StreamFailure('HOLD_TOOL_ARGUMENTS') from None
        if not isinstance(args,dict):raise StreamFailure('HOLD_TOOL_ARGUMENTS')
        # Native parser / deterministic routes share the same bounded ID rule.
        call_id=row.get('id')
        if call_id is not None and (not isinstance(call_id,str) or not 1<=len(call_id)<=160):
            raise StreamFailure('HOLD_TOOL_CALL_ID_SIZE')
        result.append({'id':call_id or f'owner_call_{step}_{index}',
                       'name':row['name'],'arguments':args})
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
    executor_reply=await asyncio.to_thread(_executor_status_reply,user_text)
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
        await asyncio.to_thread(native['audit'],'tool_step',name=name,step=1,ok=rec.get('ok'))
        yield 'token',rec['text']
        return
    if _current.download_status_query(user_text):
        yield 'token',await asyncio.to_thread(_current.inventory_reply)
        return
    messages=[dict(message) for message in payload.get('messages') or []]
    messages=await asyncio.to_thread(_current.augment_messages,messages,user_text)
    native_tools=list(native['TOOLS'])
    if _current.relevant_query(user_text):
        if any((row.get('function') or {}).get('name') in _current.NAMES for row in native_tools):
            raise StreamFailure('HOLD_OWNER_TOOL_NAME_COLLISION')
        native_tools+=_current.tools()
    req=dict(payload)
    req.pop('_agent_final',None)
    req.update(tools=native_tools,tool_choice='auto',stream=True,cache_prompt=True)
    # Native Qwen3.5 fixture verified this mode: visible tokens start directly.
    # Explicit callers may opt into deliberation; ordinary chat defaults fast.
    template=dict(req.get('chat_template_kwargs') or {})
    template.setdefault('enable_thinking',False)
    req['chat_template_kwargs']=template
    if native.get('_POOL'):
        req=native['prepare_payload'](req,cache=True)
        req['tools']=native_tools
    steps=0
    # Resolve existing deterministic routes before any model text is shown.
    # Never reinterpret already-streamed prose as an executable command.
    if not calls and native.get('_POOL'):
        deterministic=native['try_deterministic'](user_text or '')
        if deterministic and deterministic.get('name')=='clock' and deterministic.get('text'):
            yield 'token',str(deterministic['text'])
            return
        if deterministic and deterministic.get('tool'):
            calls=[{'name':deterministic['tool'],
                    'arguments':deterministic.get('arguments') or {}}]
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
                    await asyncio.to_thread(native['audit'],'tool_step',name=call['name'],
                                            step=steps,ok=rec.get('ok'))
                    text=rec.get('text') or ''
                    if not isinstance(text,str):raise StreamFailure('HOLD_TOOL_RESULT')
                    if rec.get('ok') is False and not rec.get('needs_confirmation'):
                        text='Инструмент не подтвердил выполнение действия. '+text
                    if rec.get('needs_confirmation'):
                        text+=native['confirm_marker'](rec)
                        if not text.strip():raise StreamFailure('HOLD_TOOL_CONFIRMATION')
                        yield 'token',text
                        return
                    if direct or (call['name']=='run_admin' and
                                  call['arguments'].get('action') in native['DIRECT_ADMIN']):
                        if not text.strip():raise StreamFailure('HOLD_TOOL_EMPTY')
                        yield 'token',text
                        return
                    # Tool evidence is part of the complete conversation. Never
                    # silently replace it with an 8k-character prefix; without
                    # proven context capacity, fail closed rather than fabricate
                    # a shortened observation for the model/S03 record.
                    if len(text)>2000000:
                        raise StreamFailure('HOLD_TOOL_RESULT_FULL_CONTEXT')
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
            calls=[by_id[row['id']] for row in message['tool_calls']]
            # Inspect the *original* model batch: pool deduplication must not
            # hide a second action and accidentally authorize run_admin.
            _refuse_multi_admin_batch(calls)
            if native.get('_POOL'):calls=native['dedup_calls'](calls)
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
            try:
                async with aclosing(_run(native,url,payload,user_text)) as run:
                    async for kind,text in run:
                        if kind=='token' and text:
                            answer.append(text)
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
            async with aclosing(_run(native,url,payload,user_text)) as run:
                async for kind,text in run:
                    if kind=='token':answer.append(text)
            final=''.join(answer)
            if not final.strip():raise StreamFailure('HOLD_MODEL_EMPTY')
            payload['_agent_final']=final
            return JSONResponse(native['_final_json'](final))
        except Exception:
            payload.pop('_agent_final',None)
            return JSONResponse({'error':{'code':'HOLD_OWNER_STREAM_RUNTIME'}},status_code=502)

    native['owner_completion']=owner_completion
