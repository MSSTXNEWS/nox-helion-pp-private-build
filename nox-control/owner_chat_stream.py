"""Real owner SSE over the installed NOX model and existing guarded tools.

Installed by a source-pinned agent_loop patch. No model, scheduler, credentials
or persistence store is introduced here; chat_proxy retains its S03 postflight.
"""
from __future__ import annotations

import asyncio
import hashlib
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
MAYA_ROUTE_STATE=Path('/root/nox/config/maya_ds4_owner_route_v1.json')
MAYA_API_URL='http://127.0.0.1:8080/v1/chat/completions'
MAYA_MODELS_URL='http://127.0.0.1:8080/v1/models'
MAYA_MODEL_ID='deepseek-v4.1-flash'
MAYA_ENGINE_SHA256='3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20'
_MAYA_MANAGER_PROCESS=None
_MAYA_MANAGER_LOCK=asyncio.Lock()


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


def _maya_read_file(path,limit):
    target=Path(path)
    try:
        fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
    except FileNotFoundError:
        raise
    except OSError:
        raise StreamFailure('HOLD_MAYA_RUNTIME_FILE') from None
    try:
        meta=os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid!=0
                or stat.S_IMODE(meta.st_mode)&0o022 or not 0<meta.st_size<=limit):
            raise StreamFailure('HOLD_MAYA_RUNTIME_FILE')
        with os.fdopen(fd,'rb',closefd=False) as source:
            raw=source.read(limit+1)
        if len(raw)>limit:
            raise StreamFailure('HOLD_MAYA_RUNTIME_FILE')
        return raw,meta
    finally:
        os.close(fd)


def _maya_stop_manager():
    global _MAYA_MANAGER_PROCESS
    process=_MAYA_MANAGER_PROCESS
    _MAYA_MANAGER_PROCESS=None
    if process is not None and process.returncode is None:
        try:process.terminate()
        except (OSError,ProcessLookupError):pass


def _maya_route():
    """Use only a fresh owner-supervisor grant; absent/disabled preserves the current route."""
    try:
        raw,meta=_maya_read_file(MAYA_ROUTE_STATE,8192)
    except FileNotFoundError:
        return None
    except StreamFailure:
        _maya_stop_manager()
        raise
    try:
        route=json.loads(raw)
    except (TypeError,ValueError):
        _maya_stop_manager()
        raise StreamFailure('HOLD_MAYA_ROUTE_CONFIG') from None
    if not isinstance(route,dict) or route.get('schema')!='NOX_MAYA_DS4_OWNER_ROUTE_V1':
        _maya_stop_manager()
        raise StreamFailure('HOLD_MAYA_ROUTE_CONFIG')
    if type(route.get('enabled')) is not bool:
        _maya_stop_manager()
        raise StreamFailure('HOLD_MAYA_ROUTE_CONFIG')
    if not route['enabled']:
        _maya_stop_manager()
        return None
    if not 0<=time.time()-meta.st_mtime<=30:
        _maya_stop_manager()
        raise StreamFailure('HOLD_MAYA_ROUTE_STATE_STALE')
    if (route.get('provider')!='maya_ds4' or route.get('api_url')!=MAYA_API_URL
            or route.get('models_url')!=MAYA_MODELS_URL or route.get('model')!=MAYA_MODEL_ID):
        _maya_stop_manager()
        raise StreamFailure('HOLD_MAYA_ROUTE_CONFIG')
    if route.get('owner_stop') is not False:
        _maya_stop_manager()
        raise StreamFailure('HOLD_OWNER_STOP')
    if (route.get('lease_valid') is not True
            or type(route.get('lease_expires_epoch')) is not int
            or route['lease_expires_epoch']<=time.time()):
        _maya_stop_manager()
        raise StreamFailure('HOLD_MAYA_LEASE')
    if route.get('resources_reserved') is not True or route.get('model_pack_verified') is not True:
        _maya_stop_manager()
        raise StreamFailure('HOLD_MAYA_RESOURCE_OR_PACK_GATE')
    for field in ('model_pack_receipt_sha256','manager_python_sha256',
                  'server_config_sha256','server_module_sha256'):
        value=route.get(field)
        if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value):
            _maya_stop_manager()
            raise StreamFailure('HOLD_MAYA_ROUTE_CONFIG')
    for field in ('manager_python','manager_cwd','server_config_path','model_pack_dir'):
        value=route.get(field)
        if not isinstance(value,str) or not Path(value).is_absolute():
            _maya_stop_manager()
            raise StreamFailure('HOLD_MAYA_ROUTE_CONFIG')
    key=os.environ.get('NOX_MAYA_API_KEY')
    route['_headers']={'Authorization':'Bearer '+key} if key else {}
    return route


def _maya_server_config(route):
    """Validate supervisor-pinned files, then build the official serve.server argv."""
    python=Path(route['manager_python'])
    cwd=Path(route['manager_cwd'])
    config_path=Path(route['server_config_path'])
    try:
        python_raw,python_meta=_maya_read_file(python,256*1024*1024)
        source_raw,source_meta=_maya_read_file(cwd/'serve/server.py',16*1024*1024)
        config_raw,config_meta=_maya_read_file(config_path,1024*1024)
        config=json.loads(config_raw)
        if (not os.access(python,os.X_OK)
                or hashlib.sha256(python_raw).hexdigest()!=route['manager_python_sha256']
                or hashlib.sha256(source_raw).hexdigest()!=route['server_module_sha256']
                or hashlib.sha256(config_raw).hexdigest()!=route['server_config_sha256']):
            raise ValueError('pin')
        if not isinstance(config,dict) or config.get('model_name')!=MAYA_MODEL_ID:
            raise ValueError('model')
        engine=config.get('exe')
        args=config.get('args')
        pack_arg=args[args.index('--pack')+1] if isinstance(args,list) else None
        pack=Path(route['model_pack_dir']).resolve(strict=True)
        if Path(pack_arg).resolve(strict=True)!=pack:
            raise ValueError('pack')
        engine_raw,engine_meta=_maya_read_file(engine,256*1024*1024)
        if hashlib.sha256(engine_raw).hexdigest()!=MAYA_ENGINE_SHA256:
            raise ValueError('engine')
        configured_cwd=config.get('cwd')
        if (config.get('gpu') not in (None,[0,1]) or config.get('port',8080)!=8080
                or (configured_cwd is not None
                    and Path(configured_cwd).resolve()!=Path(route['manager_cwd']).resolve())):
            raise ValueError('runtime')
    except (OSError,ValueError,TypeError,AttributeError,IndexError,StreamFailure):
        raise StreamFailure('HOLD_MAYA_RUNTIME_PIN') from None
    if config.get('api_key') and not route['_headers']:
        raise StreamFailure('HOLD_MAYA_API_KEY_UNAVAILABLE')
    return [str(python),'-m','serve.server','--engine','maya','--config',str(config_path),
            '--host','127.0.0.1','--port','8080'],str(cwd)


async def _maya_probe(client,route):
    try:
        response=await client.get(MAYA_MODELS_URL,headers=route['_headers'],timeout=5.0)
    except (httpx.ConnectError,httpx.ConnectTimeout):
        return 'offline'
    except httpx.HTTPError:
        raise StreamFailure('HOLD_MAYA_API_UNAVAILABLE') from None
    if response.status_code in (401,403):
        raise StreamFailure('HOLD_MAYA_API_AUTH')
    if response.status_code==503:
        return 'loading'
    if response.status_code!=200:
        raise StreamFailure('HOLD_MAYA_API_HTTP')
    try:
        doc=response.json()
        rows=doc.get('data')
        if not isinstance(rows,list):
            raise ValueError('models')
        model=next((row for row in rows if isinstance(row,dict) and row.get('id')==MAYA_MODEL_ID),None)
        if model is None:
            raise StreamFailure('HOLD_MAYA_MODEL_IDENTITY')
        status=model.get('status')
        value=status.get('value') if isinstance(status,dict) else None
        if value=='loaded':
            return 'ready'
        if value in ('loading','starting','unloading'):
            return 'loading'
        raise StreamFailure('HOLD_MAYA_MODEL_NOT_LOADED')
    except StreamFailure:
        raise
    except (AttributeError,TypeError,ValueError):
        raise StreamFailure('HOLD_MAYA_MODELS_RESPONSE') from None


async def _ensure_maya_server(client,route):
    """Launch only the official Maya API manager after fresh owner, lease, resource and pack gates."""
    global _MAYA_MANAGER_PROCESS
    state=await _maya_probe(client,route)
    if state=='ready':
        return
    if state=='loading':
        raise StreamFailure('HOLD_MAYA_ENGINE_STARTING')
    async with _MAYA_MANAGER_LOCK:
        state=await _maya_probe(client,route)
        if state=='ready':
            return
        if state=='loading':
            raise StreamFailure('HOLD_MAYA_ENGINE_STARTING')
        if _MAYA_MANAGER_PROCESS is not None and _MAYA_MANAGER_PROCESS.returncode is None:
            raise StreamFailure('HOLD_MAYA_ENGINE_STARTING')
        argv,cwd=_maya_server_config(route)
        env=os.environ.copy()
        env['CUDA_VISIBLE_DEVICES']='0,1'
        try:
            _MAYA_MANAGER_PROCESS=await asyncio.create_subprocess_exec(
                *argv,cwd=cwd,env=env,stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True)
        except (OSError,ValueError):
            _MAYA_MANAGER_PROCESS=None
            raise StreamFailure('HOLD_MAYA_MANAGER_START') from None
        for _ in range(8):
            await asyncio.sleep(0.5)
            if _MAYA_MANAGER_PROCESS.returncode is not None:
                raise StreamFailure('HOLD_MAYA_MANAGER_EXIT')
            state=await _maya_probe(client,route)
            if state=='ready':
                return
            if state=='loading':
                raise StreamFailure('HOLD_MAYA_ENGINE_STARTING')
        raise StreamFailure('HOLD_MAYA_ENGINE_STARTING')


async def _model_events(client, url, payload, *, model='maya', headers=None):
    """Forward content immediately; assemble function-call arguments privately."""
    request=dict(payload,model=model,stream=True,cache_prompt=True)
    text=[];calls={};finished=None;complete=False;size=0
    async with client.stream('POST',url,json=request,headers=headers,timeout=180.0) as response:
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
    maya_route=await asyncio.to_thread(_maya_route)
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
            if maya_route:
                await _ensure_maya_server(client,maya_route)
                model_url=MAYA_API_URL
                model_id=MAYA_MODEL_ID
                model_headers=maya_route['_headers']
            else:
                model_url=url
                model_id='maya'
                model_headers=None
            async with aclosing(_model_events(client,model_url,model_request,
                                              model=model_id,headers=model_headers)) as model_stream:
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
