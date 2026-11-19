"""Apply scoped startup STOP to the pinned native owner NDJSON bridge."""
from hashlib import sha256


BRIDGE = 'nox_v29_chat_bridge.py'
PREIMAGE = '29121089891a27a0ae28795d1240788421320743a17370858c4d53aca1789e8b'

_STARTUP = r'''            wire=None;buffer='';answer='';complete=False
            try:
                yield _jsonl({'type':'preparing','stream_mode':'NATIVE_TOKEN_STREAM'})
                # t141u keepalive: blank NDJSON line every 15 s while the model prefills (UI skips blank lines; stops Cloudflare 524)
                _ka_task=asyncio.ensure_future(trusted['_proxy_completion'](
                    payload, nox_cortex_dialog=dialog_id, nox_cortex_stop=cancel.is_set))
                while True:
                    _ka_done,_=await asyncio.wait({_ka_task},timeout=15)
                    if _ka_done:break
                    yield '\n'
                wire=_ka_task.result()
'''

_STARTUP_STOP = r'''            wire=None;buffer='';answer='';complete=False
            startup_task = startup_stop = chunk_task = None
            try:
                yield _jsonl({'type':'preparing','stream_mode':'NATIVE_TOKEN_STREAM'})
                if cancel.is_set():
                    yield _jsonl({'type':'error','error':'STREAM_STOP_REQUESTED'})
                    return
                startup_task = asyncio.ensure_future(trusted['_proxy_completion'](
                    payload, nox_cortex_dialog=dialog_id, nox_cortex_stop=cancel.is_set))
                startup_stop = asyncio.create_task(cancel.wait())
                while True:
                    await asyncio.wait({startup_task, startup_stop}, timeout=15,
                                       return_when=asyncio.FIRST_COMPLETED)
                    if cancel.is_set():
                        startup_task.cancel()
                        yield _jsonl({'type':'error','error':'STREAM_STOP_REQUESTED'})
                        return
                    if startup_task.done():
                        break
                    yield '\n'
                startup_stop.cancel()
                wire = startup_task.result()
'''

_CLOSE = '''            finally:
                if active.get(key) is cancel:active.pop(key,None)
                if wire is not None and hasattr(getattr(wire,'body_iterator',None),'aclose'):
                    try:await wire.body_iterator.aclose()
                    except Exception:pass
'''

_CLOSE_PENDING = '''            finally:
                # A client disconnect can cancel the Starlette streaming scope.
                from anyio import CancelScope
                with CancelScope(shield=True):
                    try:
                        pending = [task for task in (startup_task, startup_stop, chunk_task)
                                   if task is not None]
                        for task in pending:
                            if not task.done():
                                task.cancel()
                        if pending:
                            await asyncio.gather(*pending, return_exceptions=True)
                        # STOP or disconnect can win after the response is ready
                        # but before the streaming generator has adopted it.
                        if wire is None and startup_task is not None and not startup_task.cancelled():
                            try:
                                wire = startup_task.result()
                            except Exception:
                                pass
                        close = getattr(getattr(wire, 'body_iterator', None), 'aclose', None)
                        if close is not None:
                            try:
                                await close()
                            except Exception:
                                pass
                    finally:
                        if active.get(key) is cancel:
                            active.pop(key, None)
'''


def transform(name: str, source: bytes) -> bytes:
    if name != BRIDGE or sha256(source).hexdigest() != PREIMAGE:
        raise RuntimeError('HOLD_OWNER_NDJSON_STOP_PREIMAGE')

    content = source.decode('utf-8')
    replacements = (
        (_STARTUP, _STARTUP_STOP),
        ('''                    _ka_task=asyncio.ensure_future(_next_native_chunk_or_stop(upstream,cancel))
                    while True:
                        _ka_done,_=await asyncio.wait({_ka_task},timeout=15)
                        if _ka_done:break
                        yield '\\n'
                    event,chunk=_ka_task.result()
''', '''                    chunk_task=asyncio.ensure_future(_next_native_chunk_or_stop(upstream,cancel))
                    while True:
                        _ka_done,_=await asyncio.wait({chunk_task},timeout=15)
                        if _ka_done:break
                        yield '\\n'
                    event,chunk=chunk_task.result()
'''),
        (_CLOSE, _CLOSE_PENDING),
    )
    for old, new in replacements:
        if content.count(old) != 1:
            raise RuntimeError('HOLD_OWNER_NDJSON_STOP_ANCHOR')
        content = content.replace(old, new, 1)

    updated = content.encode('utf-8')
    compile(updated, BRIDGE, 'exec')
    return updated
