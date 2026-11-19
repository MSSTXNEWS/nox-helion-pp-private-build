"""NOX V105: native-only WEB V29.3 stream translation, with real S03 readback.

Register on EXISTING authenticated nox-proxy app. It never starts a model, DB,
worker daemon or alternative scheduler. Do not use if the existing source did
not pass SHA and same-owner acceptance.
"""
from __future__ import annotations
import asyncio
import codecs
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Mapping
from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse


def _jsonl(frame: Mapping) -> str:
    return json.dumps(frame, ensure_ascii=False, separators=(',', ':')) + '\n'


def _readback(question: str, answer: str) -> dict | None:
    """Verify an actual committed native S03 user+answer record. Never log text."""
    if len(question.strip()) < 3 or len(answer.strip()) < 2:
        return None
    try:
        import s03_memory
        db = Path(s03_memory.DB)
        if not db.is_file() or db.is_symlink():
            return None
        with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True, timeout=3) as conn:
            conn.execute('PRAGMA query_only=ON')
            row = conn.execute(
                'SELECT id,sha256 FROM s03_items '
                'WHERE instr(text, ?) > 0 AND instr(text, ?) > 0 '
                'ORDER BY ts DESC LIMIT 1',
                (question[:160], answer[:150]),
            ).fetchone()
        if not row or not isinstance(row[0], str) or not isinstance(row[1], str):
            return None
        if len(row[0]) < 6 or len(row[1]) != 64:
            return None
        return {'record_id': row[0], 'sha256': row[1]}
    except (OSError, sqlite3.Error, ValueError, ImportError, AttributeError):
        return None


def _token_from_delta(line: str) -> tuple[str, str]:
    """Return only model content, never chain-of-thought/reasoning fields."""
    if not line.startswith('data:'):
        return ('', '')
    data = line[5:].strip()
    if data == '[DONE]':
        return ('done', '')
    try:
        obj = json.loads(data)
    except (ValueError, TypeError):
        return ('', '')
    if not isinstance(obj, dict):
        return ('', '')
    for choice in obj.get('choices') or []:
        if not isinstance(choice, dict):
            continue
        part = (choice.get('delta') or {}).get('content')
        if isinstance(part, str) and part:
            return ('delta', part)
    return ('', '')


def register_native_v29_chat(app, trusted: dict) -> None:
    """Register two real owner-only operations; optional features stay unclaimed."""
    for name in ('_session_ok', '_unauthorized', '_proxy_completion'):
        if not callable(trusted.get(name)):
            raise RuntimeError('HOLD_MISSING_EXISTING_NATIVE_OWNER_' + name)
    if any(getattr(route, 'path', '') in ('/api/nox/chat/stream', '/api/nox/stop')
           for route in app.routes):
        raise RuntimeError('HOLD_ROUTE_ALREADY_REGISTERED')

    # The browser's V29 request id isn't included in the submitted JSON.
    # A session-bound cancellation flag controls active streaming; do not
    # claim the underlying GPU operation stopped without a native receipt.
    active: dict[str, asyncio.Event] = {}

    def _scope(request: Request) -> str | None:
        if not request.cookies:
            return None
        raw = json.dumps(sorted(request.cookies.items()), ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    @app.post('/api/nox/chat/stream')
    async def native_v29_chat_stream(request: Request):
        if not trusted['_session_ok'](request):
            return trusted['_unauthorized']()
        try:
            item = await request.json()
        except Exception:
            return JSONResponse({'error': 'INVALID_JSON'}, status_code=400)
        if not isinstance(item, dict):
            return JSONResponse({'error': 'INVALID_BODY'}, status_code=400)
        text = item.get('message')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 8000:
            return JSONResponse({'error': 'INVALID_MESSAGE'}, status_code=422)
        # Until native scope ACL and history API are accepted, never accept a
        # client-chosen dialog id as owner memory authority.
        dialog_id = item.get('dialog_id')
        if dialog_id is not None:
            # A client-supplied dialog is never proof of memory ownership.
            verifier = trusted.get('_verify_dialog_scope')
            receipt_reader = trusted.get('_readback_dialog_receipt')
            if (not isinstance(dialog_id, str) or not 1 <= len(dialog_id) <= 128
                    or not callable(verifier) or not callable(receipt_reader)):
                return JSONResponse({'error': 'HOLD_DIALOG_SCOPE_NOT_BOUND'}, status_code=409)
            try:
                permitted = await asyncio.to_thread(verifier, request, dialog_id)
            except Exception:
                permitted = False
            if permitted is not True:
                return JSONResponse({'error': 'HOLD_DIALOG_SCOPE_NOT_BOUND'}, status_code=409)
        rows = item.get('history') or []
        if not isinstance(rows, list) or len(rows) > 24:
            return JSONResponse({'error': 'HOLD_HISTORY_LIMIT'}, status_code=422)
        history = []
        bytes_used = 0
        for row in rows:
            if not isinstance(row, dict) or row.get('role') not in ('user', 'assistant'):
                return JSONResponse({'error': 'HOLD_HISTORY_ROLE'}, status_code=422)
            body = row.get('content')
            if not isinstance(body, str) or len(body) > 8000:
                return JSONResponse({'error': 'HOLD_HISTORY_CONTENT'}, status_code=422)
            bytes_used += len(body.encode('utf8'))
            if bytes_used > 121000:
                return JSONResponse({'error': 'HOLD_HISTORY_SIZE'}, status_code=422)
            history.append({'role': row['role'], 'content': body})
        payload = {'messages': history + [{'role': 'user', 'content': text}],
                   '_owner': True, 'stream': True}
        if dialog_id is not None:
            payload['dialog_id'] = dialog_id
        scope = _scope(request)
        if scope is None:
            return JSONResponse({'error': 'HOLD_SESSION_COOKIE_SCOPE'}, status_code=401)
        if scope in active:
            return JSONResponse({'error': 'HOLD_ACTIVE_SESSION_STREAM'}, status_code=409)
        cancel = asyncio.Event()
        active[scope] = cancel

        async def generate():
            model_buffer = ''
            finished = False
            reply = ''
            response = None
            try:
                yield _jsonl({'type': 'preparing', 'stream_mode': 'NATIVE_TOKEN_STREAM'})
                response = await trusted['_proxy_completion'](payload)
                if not hasattr(response, 'body_iterator'):
                    yield _jsonl({'type': 'error', 'error': 'HOLD_NATIVE_STREAM_MISSING'})
                    return
                yield _jsonl({'type': 'start', 'model': 'NOX HELION',
                              'stream_mode': 'NATIVE_TOKEN_STREAM'})
                dec = codecs.getincrementaldecoder('utf8')('replace')
                async for piece in response.body_iterator:
                    if cancel.is_set():
                        yield _jsonl({'type': 'error', 'error': 'STREAM_STOP_REQUESTED'})
                        return
                    b = piece if isinstance(piece, bytes) else str(piece).encode('utf8')
                    model_buffer += dec.decode(b)
                    if len(model_buffer) > 300000:
                        yield _jsonl({'type': 'error', 'error': 'HOLD_SSE_FRAME_LIMIT'})
                        return
                    while '\n' in model_buffer:
                        line, model_buffer = model_buffer.split('\n', 1)
                        kind, value = _token_from_delta(line.strip())
                        if kind == 'done':
                            finished = True
                        elif kind == 'delta':
                            if len(reply) + len(value) > 2000000:
                                yield _jsonl({'type': 'error', 'error': 'HOLD_OUTPUT_SIZE'})
                                return
                            reply += value
                            yield _jsonl({'type': 'delta', 'text': value})
                if not finished or not reply.strip() or cancel.is_set():
                    yield _jsonl({'type': 'error', 'error': 'HOLD_INCOMPLETE_NATIVE_RESPONSE'})
                    return
                # The original V98 postflight has now finished. Check the
                # single existing S03 database by exact question+answer text.
                if dialog_id is not None:
                    try:
                        proof = await asyncio.to_thread(
                            trusted['_readback_dialog_receipt'],
                            request, dialog_id, text, reply)
                    except Exception:
                        proof = None
                    if (not isinstance(proof, dict)
                            or proof.get('dialog_id') != dialog_id
                            or not isinstance(proof.get('record_id'), str)
                            or not proof['record_id']):
                        proof = None
                else:
                    proof = await asyncio.to_thread(_readback, text, reply)
                if proof is None:
                    yield _jsonl({'type': 'error', 'error': 'HOLD_S03_COMMIT_NOT_VERIFIED'})
                    return
                done = {'type': 'done', 'model': 'NOX HELION',
                        'saved': True, 's03_integrated': True,
                        'stream_mode': 'NATIVE_TOKEN_STREAM',
                        'exchange_id': proof['record_id']}
                if dialog_id is not None:
                    done['dialog_id'] = dialog_id
                yield _jsonl(done)
            except asyncio.CancelledError:
                raise
            except Exception:
                yield _jsonl({'type': 'error', 'error': 'HOLD_EXISTING_ONEHOST_RUNTIME'})
            finally:
                if scope in active and active[scope] is cancel:
                    del active[scope]
                if response is not None:
                    iterator = getattr(response, 'body_iterator', None)
                    if iterator is not None and hasattr(iterator, 'aclose'):
                        try:
                            await iterator.aclose()
                        except Exception:
                            pass
        return StreamingResponse(generate(), media_type='application/x-ndjson',
                                 headers={'Cache-Control': 'no-store',
                                          'X-Accel-Buffering': 'no'})

    @app.post('/api/nox/stop')
    async def native_v29_stream_stop(request: Request):
        if not trusted['_session_ok'](request):
            return trusted['_unauthorized']()
        scope = _scope(request)
        if scope is None or scope not in active:
            return JSONResponse({'status': 'HOLD', 'reason': 'NO_ACTIVE_SESSION_STREAM'},
                                status_code=409)
        active[scope].set()
        return JSONResponse({'status': 'STOP_REQUESTED',
                             'stream_cancellation_signalled': True,
                             'gpu_stop_verified': False})
