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
    target=Path(path) if path is not None else EXECUTOR_STATUS
    try:
        fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
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
        observed=datetime.fromtimestamp(meta.st_mtime,timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        return (f'Сейчас у диспетчера настроено {n} исполнителей: занято {busy}, свободно {n-busy}. '
                f'NOX — отдельный координатор и чат (1). Схема: {n} исполнителей + NOX.\n'
                f'Исполнители: {", ".join(ids)}.\nИсточник: свежий статус диспетчера, {observed}.')
    except (OSError,ValueError,TypeError,OverflowError):
        return unknown


async def _model_events(client, url, payload):
    """Forward content immediately; assemble function-call arguments privately."""
    request=dict(payload,model='maya',stream=True,cache_prompt=True)
    text=[];calls={};finished=None;complete=False;size=0
    async with client.stream('POST',url,json=request,timeout=180.0) as response:
        if response.status_code!=200:
            raise StreamFailure('HOLD_MODEL_HTTP')
        async for line in response.aiter_lines():
            if not line or line.startswith(':'):
                continue
            if not line.startswith('data:'):
                raise StreamFailure('HOLD_MODEL_SSE_FRAME')
            wire=line[5:].strip()
            if wire=='[DONE]':
                complete=True
                break
            if len(wire)>300000:
                raise StreamFailure('HOLD_MODEL_SSE_SIZE')
            try:
                doc=json.loads(wire)
                if not isinstance(doc,dict) or doc.get('error'):
                    raise ValueError('error')
                choices=doc.get('choices')
                if choices==[] and isinstance(doc.get('usage'),dict):
                    continue
                if not isinstance(choices,list) or len(choices)!=1:
                    raise ValueError('choices')
                choice=choices[0]
                delta=choice.get('delta') or {}
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
                fragments=delta.get('tool_calls') or []
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
                    function=fragment.get('function') or {}
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
        args=row.get('arguments') or {}
        if isinstance(args,str):
            try:args=json.loads(args)
            except ValueError:raise StreamFailure('HOLD_TOOL_ARGUMENTS') from None
        if not isinstance(args,dict):raise StreamFailure('HOLD_TOOL_ARGUMENTS')
        result.append({'id':row.get('id') or f'owner_call_{step}_{index}',
                       'name':row['name'],'arguments':args})
    return result


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
    calls=native['_direct_admin_calls'](user_text or '') or []
    direct=bool(calls)
    if direct:calls=calls[:1]
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
                    messages.append({'role':'tool','tool_call_id':call['id'],
                                     'name':call['name'],'content':text[:8000]})
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
            if native.get('_POOL'):calls=native['dedup_calls'](calls)
            if not calls:raise StreamFailure('HOLD_TOOL_PARSE')
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
            except asyncio.CancelledError:
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
