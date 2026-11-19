"""Preserve authenticated thread context and route explicit Drive checks."""

from hashlib import sha256
import json
import re

PROXY_SHA256 = '54b1932c3e408c91c3086de994eb9b85709d65066746b5ca520582829ab94d89'
NATIVE_BRIDGE_SHA256 = '3b1f1c22279b2fbca3be03ef53579e8dd93ab3ea44a3c5404e7584f07e3bbf1b'
DIALOG_ID = re.compile(r'[a-f0-9]{32}')
DRIVE_ALIAS = re.compile(
    r'\b(?:google\s*(?:drive|диск\w*)|gdrive|диск\w*\s+гугла|'
    r'(?:гуг(?:у|е)?л|гул)[ -]+(?:диск\w*|драйв\w*))\b',
    re.IGNORECASE,
)
STATUS_REQUEST = re.compile(
    r'\b(?:проверь\w*|проверка|проверить|доступ\w*|досту|подключ\w*|работает|статус|'
    r'есть\s+ли|can\s+you\s+access|check|connection|access|connected|status)\b',
    re.IGNORECASE,
)
ADDITIONAL_ACTION = re.compile(
    r'\b(?:и|and)\s+(?:[а-яё]+\s+){0,2}'
    r'(?:загрузи\w*|выгрузи\w*|скачай\w*|запиши\w*|удали\w*|перенеси\w*|'
    r'сервер\w*|dropbox|onedrive|yandex|яндекс|upload|download|write|delete)\b',
    re.IGNORECASE,
)
STATUS_STATES = {'CONNECTED', 'NOT_CONNECTED', 'UNKNOWN', 'CHECKING'}
UNAVAILABLE = 'Я не смог подтвердить доступ к Google Drive. Запись не проверялась.'
HEALTH = None


def _health():
    global HEALTH
    if HEALTH is None:
        from owner_drive_chat_health import DriveHealth
        from owner_native_drive_probe import probe

        HEALTH = DriveHealth(probe)
    return HEALTH


def _explicit_drive_status(question):
    return bool(len(question) <= 600 and DRIVE_ALIAS.search(question) and STATUS_REQUEST.search(question)
                and not ADDITIONAL_ACTION.search(question))


def _drive_message(report):
    if (type(report) is not dict or report.get('schema') != 'NOX_WEB_DRIVE_HEALTH_V1'
            or report.get('state') not in STATUS_STATES
            or report.get('write_access') != 'NOT_TESTED'):
        return UNAVAILABLE
    if report['state'] == 'CONNECTED' and report.get('read_access') != 'VERIFIED':
        return UNAVAILABLE
    message = report.get('message')
    if (not isinstance(message, str) or not 1 <= len(message) <= 180
            or 'Google Drive' not in message or '\n' in message or '\r' in message):
        return UNAVAILABLE
    return message


def _stop_response():
    from fastapi.responses import JSONResponse

    return JSONResponse({'error': {'message': 'STREAM_STOP_REQUESTED'}}, status_code=409)


def _stream_message(message, stop_requested):
    from fastapi.responses import StreamingResponse

    async def generate():
        if stop_requested():
            return
        frame = {'choices': [{'delta': {'content': message}}]}
        yield 'data: ' + json.dumps(frame, ensure_ascii=False, separators=(',', ':')) + '\n\n'
        if not stop_requested():
            yield 'data: [DONE]\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-store'})


async def _explicit_drive_response(stop_requested):
    if stop_requested():
        return _stop_response()
    try:
        report = await _health().status(wait_for_result=True)
    except Exception:
        report = None
    if stop_requested():
        return _stop_response()
    return _stream_message(_drive_message(report), stop_requested)


def _prefer_context(question, messages):
    from nox_dialog_followup import resolve_followup

    if resolve_followup(question, []) is not None:
        return True
    # An arbitrary short question can reference any noun or prior answer.
    # The native bridge supplies this history after authenticating the dialog.
    # Keep the existing message list untouched and let the model interpret it.
    if (len(question) > 64 or '\n' in question or not isinstance(messages, list)
            or not messages or messages[-1] != {'role': 'user', 'content': question}):
        return False
    return any(isinstance(row, dict) and row.get('role') == 'user'
               and isinstance(row.get('content'), str) and row['content'].strip()
               for row in messages[:-1])


async def prepare_owner_turn(question, dialog_id, stop_requested, messages):
    """Return a tool response or the decision to preserve semantic routing."""
    if not (isinstance(question, str) and question.strip() and isinstance(dialog_id, str)
            and DIALOG_ID.fullmatch(dialog_id) and callable(stop_requested)):
        return None, False
    if _explicit_drive_status(question):
        return await _explicit_drive_response(stop_requested), False
    return None, _prefer_context(question, messages)


def transform_proxy(raw: bytes) -> bytes:
    """Add a single owner gate to the exact deployed streaming proxy."""
    if sha256(raw).hexdigest() != PROXY_SHA256:
        raise RuntimeError('HOLD_DRIVE_PROXY_PREIMAGE')
    source = raw.decode('utf-8')
    turn_anchor = '    _utext = _last_user_text(body)\n'
    classifier_anchor = '    _und = None if _self_query else await _nox_chat_asyncio.to_thread(\n'
    if source.count(turn_anchor) != 1 or source.count(classifier_anchor) != 1:
        raise RuntimeError('HOLD_DRIVE_PROXY_ANCHOR')
    turn_hook = (
        '    _nox_contextual = False\n'
        '    if body.get("_owner") is True and bool(body.get("stream")) and nox_cortex_dialog and callable(nox_cortex_stop):\n'
        '        from owner_drive_chat_route import prepare_owner_turn as _nox_prepare_turn\n'
        '        _nox_direct, _nox_contextual = await _nox_prepare_turn(\n'
        '            _utext, nox_cortex_dialog, nox_cortex_stop, body.get("messages"))\n'
        '        if _nox_direct is not None:\n'
        '            return _wrap_ttft(_nox_direct, t_gate, _utext)\n'
    )
    source = source.replace(turn_anchor, turn_anchor + turn_hook, 1)
    source = source.replace(classifier_anchor,
        '    _und = None if _self_query or _nox_contextual else await _nox_chat_asyncio.to_thread(\n', 1)
    candidate = source.encode('utf-8')
    compile(candidate, 'chat_proxy.py', 'exec')
    return candidate
