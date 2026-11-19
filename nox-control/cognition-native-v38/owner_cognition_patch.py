"""Apply the owner-only V38 hooks to two pinned native source files."""
from hashlib import sha256


PREIMAGES = {
    'chat_proxy.py': 'cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb',
    'nox_v29_chat_bridge.py': '2d7145293fa5566fee38a61e772780b4b0dd0e2d1bcad71b5ceedf77974a75a7',
}


def _replace(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('HOLD_COGNITION_PATCH_ANCHOR')
    return source.replace(old, new, 1)


def _proxy(source):
    source = _replace(source, 'def _augment(user_text: str, dialog_msgs=None) -> str:',
                      'def _augment(user_text: str, dialog_msgs=None, *, cortex_context="", scoped_s03=False) -> str:')
    source = _replace(source, '    mem = _scrub_memory_context(_s03_augment(retrieve_text) or "")',
                      '    if cortex_context:\n'
                      '        parts.insert(0, cortex_context)\n'
                      '    recall = _textbook_snip if scoped_s03 else _s03_augment\n'
                      '    mem = _scrub_memory_context(recall(retrieve_text) or "")')
    source = _replace(source, '    if mem:\n        parts.append(mem)\n    try:\n        if NOX_MEM is not None:',
                      '    if mem:\n        parts.append(mem)\n    try:\n        if not scoped_s03 and NOX_MEM is not None:')
    source = _replace(source, 'def _build_messages(body: dict) -> list:', '''def _v38_dialog_context(dialog_id, user_text, stop_active):
    if not dialog_id:
        return ''
    try:
        from nox_v38_native_context import build
        context, receipt = build(dialog_id, user_text, s03_recall,
                                 {'persona_enabled': False, 'stop_active': stop_active})
    except Exception:
        context, receipt = '', {'state': 'HOLD_COGNITION_CONTEXT'}
    try:
        log_line(LOGS / 'proxy.log', 'nox_v38_context state={} hits={} affect={} persona={} cores={}'.format(
            receipt['state'], receipt.get('memory_hits', 0), receipt.get('affect_observed', False),
            receipt.get('persona_mode'), receipt.get('core_states', {})))
    except OSError:
        pass
    return context


def _build_messages(body: dict, *, nox_cortex_dialog=None, nox_cortex_stop=None) -> list:''')
    source = _replace(source, '    try:\n        from slim_chat_t885u import apply_system, rag_relevant, typo_only, self_state',
                      '    cortex = _v38_dialog_context(nox_cortex_dialog, user_text, nox_cortex_stop)\n'
                      '    try:\n        from slim_chat_t885u import apply_system, rag_relevant, typo_only, self_state')
    source = _replace(source, '            augmented = _augment(user_text, msgs)',
                      '            augmented = _augment(user_text, msgs, cortex_context=cortex,\n'
                      '                                 scoped_s03=bool(nox_cortex_dialog))')
    source = _replace(source, '            try:\n                from nox_cores_t899u import pre_answer_context\n'
                      '                _ctx = pre_answer_context(user_text or "", budget=0.2)\n'
                      '                if _ctx:\n                    _tail.append(',
                      '            try:\n                if not nox_cortex_dialog:\n'
                      '                    from nox_cores_t899u import pre_answer_context\n'
                      '                    _ctx = pre_answer_context(user_text or "", budget=0.2)\n'
                      '                else:\n                    _ctx = None\n'
                      '                if _ctx:\n                    _tail.append(')
    source = _replace(source, '        augmented = typo_only(user_text) if user_text else user_text\n    sys = str(sys)',
                      '        augmented = typo_only(user_text) if user_text else user_text\n'
                      '    if cortex and not _need_mem:\n'
                      '        augmented += "\\n\\n---\\n" + cortex\n'
                      '    sys = str(sys)')
    source = _replace(source, 'async def _proxy_completion(body: dict):',
                      'async def _proxy_completion(body: dict, *, nox_cortex_dialog=None, nox_cortex_stop=None):')
    source = _replace(source, 'payload["messages"] = await _nox_chat_asyncio.to_thread(lambda: _build_messages(body))',
                      'payload["messages"] = await _nox_chat_asyncio.to_thread(\n'
                      '            _build_messages, body, nox_cortex_dialog=nox_cortex_dialog,\n'
                      '            nox_cortex_stop=nox_cortex_stop)')
    source = _replace(source, '                lambda: _trim_ctx(_build_messages(body), selected_url=url,',
                      '                lambda: _trim_ctx(_build_messages(\n'
                      '                    body, nox_cortex_dialog=nox_cortex_dialog if _owner else None,\n'
                      '                    nox_cortex_stop=nox_cortex_stop), selected_url=url,')
    source = _replace(source, '    if _owner and _nox_training_query(_utext):\n',
                      '    if callable(nox_cortex_stop) and nox_cortex_stop():\n'
                      '        from fastapi.responses import JSONResponse\n'
                      '        return JSONResponse({"error": {"message": "STREAM_STOP_REQUESTED"}}, status_code=409)\n'
                      '    if _owner and _nox_training_query(_utext):\n')
    source = _replace(source, '        Path("/root/nox/state/chat_active").write_text(str(time.time()), encoding="utf-8")', '''        import os
        import stat
        marker = "/root/nox/state/chat_active"
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        fd = os.open(marker, flags, 0o644)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
                return
            if stat.S_IMODE(info.st_mode) != 0o644:
                os.fchmod(stream.fileno(), 0o644)
            stream.truncate(0)
            stream.write(str(time.time()))''')
    return source


def _bridge(source):
    source = _replace(source, "                _up = asyncio.ensure_future(trusted['_proxy_completion'](payload))",
                      "                _up = asyncio.ensure_future(trusted['_proxy_completion'](\n"
                      "                    payload, nox_cortex_dialog=dialog_id))")
    source = _replace(source, "                _ka_task=asyncio.ensure_future(trusted['_proxy_completion'](payload))",
                      "                _ka_task=asyncio.ensure_future(trusted['_proxy_completion'](\n"
                      "                    payload, nox_cortex_dialog=dialog_id, nox_cortex_stop=cancel.is_set))")
    source = _replace(source, '                    proof=await asyncio.to_thread(_readback,question,answer,started)',
                      '                    proof=await asyncio.to_thread(_readback,question,answer,started,True)\n'
                      '                    if proof is None:\n'
                      '                        proof=await asyncio.to_thread(_readback,question,answer,started)')
    return source


def transform(name: str, source: bytes) -> bytes:
    if name not in PREIMAGES or sha256(source).hexdigest() != PREIMAGES[name]:
        raise RuntimeError('HOLD_COGNITION_PATCH_PREIMAGE')
    patch = _proxy if name == 'chat_proxy.py' else _bridge
    updated = patch(source.decode('utf-8')).encode('utf-8')
    compile(updated, name, 'exec')
    return updated
