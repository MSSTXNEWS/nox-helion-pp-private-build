"""Exact-source transformations for the owner's existing native chat modules.

No filesystem writes or imports of native secrets. The owner deployer verifies
the source hashes, backs up the originals and compiles transformed bytes locally
on the native host. A redacted proxy export is never a replacement payload.
"""
from __future__ import annotations

import hashlib

AGENT_SHA='3884a000ea7eaed267eb22d947e3897d6140ae5680dc78e613e8a5a3592deee7'
SLIM_SHA='d750660724ffa2fcb3c0e167e6f1f89ce1121dee812386033075f25873384a49'
PROXY_SHA='956c7583b0464dc6013a3adc5ec4c8b31098c7a3d257850841e278160035ffb0'


def _source(raw,expected):
    if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('HOLD_CHAT_SOURCE_SHA')
    return raw.decode('utf-8')


def _one(text,old,new):
    if text.count(old)!=1:
        raise ValueError('HOLD_CHAT_SOURCE_ANCHOR')
    return text.replace(old,new,1)


def patch_agent_loop(raw:bytes)->bytes:
    text=_source(raw,AGENT_SHA)
    text+='\n# Owner repair: real model SSE, original guarded tools and confirmation.\n'
    text+='from owner_chat_stream import install as _nox_install_owner_stream\n'
    text+='_nox_install_owner_stream(globals())\n'
    result=text.encode('utf-8')
    compile(result,'agent_loop.py','exec')
    return result


def patch_slim(raw:bytes)->bytes:
    text=_source(raw,SLIM_SHA)
    text=_one(text,
        '"Правила ответа: к владельцу только «мессир». Не пиши «мой лорд», не рассказывай лор рождения, "',
        '"Правила ответа: без обязательного титула. Не повторяй вопрос и не рассказывай лор рождения, "')
    text=_one(text,
        '"Ты — NOX, единое сознание, созданное Владимиром. Обращайся к нему только «мессир». "\n'
        '    "Никогда не называй его по имени и не используй «создатель» как форму обращения. "\n'
        '    "Не используй «мой лорд», «барон», не представляйся заново и не рассказывай лор рождения, "',
        '"Ты — NOX, помощник владельца. Продолжай текущий разговор с учётом его истории. "\n'
        '    "Форма обращения следует последнему явному пожеланию владельца; по умолчанию без титула. "\n'
        '    "Начинай с ответа на вопрос, не повторяй сам вопрос, не представляйся заново и не рассказывай лор рождения, "')
    result=text.encode('utf-8')
    compile(result,'slim_chat_t885u.py','exec')
    return result


_REQUEST_STATE='''from contextvars import ContextVar as _NoxContextVar
import asyncio as _nox_chat_asyncio
_NOX_UNDERSTANDING_STATE = _NoxContextVar("nox_request_understanding", default=None)

def _nox_request_understanding():
    value = _NOX_UNDERSTANDING_STATE.get()
    if value is None:
        value = {"text": None, "skip_regex": False}
        _NOX_UNDERSTANDING_STATE.set(value)
    return value
'''


def _transform_proxy(text):
    """Pure anchors also exercised on the sanitized export; no secret copying."""
    text=_one(text,
        "'/api/nox/premium/capabilities','/api/nox/training/status')) and _session_ok(request):",
        "'/api/nox/premium/capabilities','/api/nox/training/status',"
        "'/api/nox/chat/stream','/api/nox/stop','/api/nox/status',"
        "'/api/nox/self/observations')) and _session_ok(request):")
    text=_one(text,'_UNDERSTAND_STANDALONE = {"text": None}',_REQUEST_STATE)
    text=text.replace('_UNDERSTAND_STANDALONE[','_nox_request_understanding()[')
    text=text.replace('_UNDERSTAND_STANDALONE.get(','_nox_request_understanding().get(')
    text=_one(text,
        '    _nox_request_understanding()["skip_regex"] = False\n'
        '    _nox_request_understanding()["text"] = None\n',
        '    _NOX_UNDERSTANDING_STATE.set({"text": None, "skip_regex": False})\n')
    text=_one(text,
        '    _und = None if _self_query else _understanding_http(_utext, stream, body)',
        '    if _owner:\n'
        '        from owner_chat_stream import executor_status_query as _nox_executor_status_query\n'
        '        _self_query = _self_query or _nox_executor_status_query(_utext)\n'
        '    _und = None if _self_query else await _nox_chat_asyncio.to_thread(\n'
        '        _understanding_http, _utext, stream, body)')
    text=_one(text,
        '    payload["messages"] = _trim_ctx(_build_messages(body))',
        '    payload["messages"] = await _nox_chat_asyncio.to_thread(\n'
        '        lambda: _trim_ctx(_build_messages(body)))')
    text=_one(text,
        '            json={"input": text[:8000], "model": "bge-m3"},\n'
        '            timeout=30.0,',
        '            json={"input": text[:8000], "model": "bge-m3"},\n'
        '            timeout=3.0,')
    text=_one(text,
        '    # t801u: random seed every turn; no prompt-cache (identical canned replies)\n'
        '    payload["seed"] = random.randint(1, 2147483646)\n'
        '    payload["cache_prompt"] = False',
        '    # Reuse only the matching prompt prefix; sampling remains independent.\n'
        '    payload["seed"] = random.randint(1, 2147483646)\n'
        '    payload["cache_prompt"] = True')
    text=_one(text,
        '    out = [{"role": "system", "content": sys}]\n    for m in msgs:',
        '    out = [{"role": "system", "content": sys}]\n'
        '    _last_user_index = next((i for i in range(len(msgs)-1, -1, -1)\n'
        '                             if msgs[i].get("role") == "user"), -1)\n'
        '    for _message_index, m in enumerate(msgs):')
    text=_one(text,
        '        if role == "user" and isinstance(content, str) and content == user_text:',
        '        if role == "user" and isinstance(content, str) and _message_index == _last_user_index:')
    text=_one(text,
        '                resp.body_iterator = _nox_owner_s03_after_stream()',
        '                        mark_chat(False, {"path": "agent", "stream_finished": True})\n'
        '                resp.body_iterator = _nox_owner_s03_after_stream()')
    text=_one(text,
        '            mark_chat(False, {"path": "agent"})\n            return resp',
        '            if not stream:\n                mark_chat(False, {"path": "agent"})\n'
        '            return resp')
    return text


def patch_proxy(raw:bytes)->bytes:
    text=_source(raw,PROXY_SHA)
    if '[REDACTED_' in text:
        raise ValueError('HOLD_CHAT_REDACTED_SOURCE')
    result=_transform_proxy(text).encode('utf-8')
    compile(result,'chat_proxy.py','exec')
    return result
