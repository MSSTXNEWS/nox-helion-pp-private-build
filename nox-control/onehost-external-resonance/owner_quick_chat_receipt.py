"""Prove one existing native Resonance dialog through the exact external HTTPS route."""

import http.client
import json
import re
import time
from urllib.parse import urlsplit


SAFE_HOST = re.compile(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\.trycloudflare\.com')


def require(condition, reason):
    if not condition:
        raise RuntimeError('HOLD_NOX_HTTPS_' + reason)


def prove(tunnel, owner_client, *, allow_model=True):
    route = urlsplit(tunnel['url'])
    host = route.hostname or ''
    require(route.scheme == 'https' and SAFE_HOST.fullmatch(host) and route.netloc == host
            and not route.query and not route.fragment, 'ROUTE_IDENTITY')
    origin = 'https://' + host

    def request(path, cookie=None, data=None, *, stream=False):
        conn = http.client.HTTPSConnection(host, 443, timeout=150 if stream else 12)
        headers = {'Connection': 'close', 'Accept-Encoding': 'identity'}
        if cookie is not None:
            headers['Cookie'] = 'nox_chat=' + cookie
        if data is not None:
            headers['Content-Type'] = 'application/json'
            headers['Origin'] = origin
        try:
            conn.request('GET' if data is None else 'POST', path,
                         body=None if data is None else json.dumps(data, ensure_ascii=False).encode(), headers=headers)
            response = conn.getresponse()
            if stream:
                return conn, response
            body = response.read(1_000_001)
            require(len(body) <= 1_000_000, 'HTTP_RESPONSE_BOUND')
            return response.status, body
        except BaseException:
            conn.close()
            raise
        finally:
            if not stream:
                conn.close()

    page, protected, health = request('/chat'), request('/api/ui/memory/dialogs'), request('/_nox_edge_health')
    require(page[0] == 200 and b'/api/nox/chat/stream' in page[1], 'PAGE_NOT_SERVED')
    require(protected[0] == 401, 'ANONYMOUS_SESSION_GATE')
    require(health[0] == 200 and json.loads(health[1]).get('source_sha256') == tunnel['gateway_sha256'],
            'GATEWAY_IDENTITY')
    cookie = owner_client.authenticate().cookie
    require(request('/chat/session', cookie)[0] == 200, 'OWNER_SESSION')
    status, raw = request('/api/ui/memory/dialogs', cookie)
    require(status == 200, 'DIALOG_LIST')
    matches = [row['dialog_id'] for row in json.loads(raw).get('dialogs', [])
               if row.get('title') == 'NOX V38 — приёмка 7013673520']
    require(len(matches) == 1 and re.fullmatch(r'[0-9a-f]{32}', matches[0]), 'PRODUCT_DIALOG_SCOPE')
    dialog_id = matches[0]
    if not allow_model:
        return {'url': origin + '/chat', 'https': True, 'anonymous_protected': True, 'authenticated': True,
                'external_stream_verified': False, 'retained_dialog_verified': True,
                'reason': 'MEMORY_RESERVE', 'expires_unix': tunnel['expires_unix']}
    question = 'Из текущего диалога назови штабной проект одним словом. Это продолжение разговора.'
    started = time.monotonic()
    conn, response = request('/api/nox/chat/stream', cookie,
                             {'message': question, 'dialog_id': dialog_id}, stream=True)
    answer, done, first = [], None, None
    total = 0
    try:
        require(response.status == 200 and response.getheader('Content-Type', '').startswith('application/x-ndjson'),
                'NDJSON_STATUS')
        while line := response.readline(65537):
            total += len(line)
            require(len(line) <= 65536 and total <= 150000, 'STREAM_BOUND')
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get('type') == 'delta' and isinstance(event.get('text'), str):
                if first is None:
                    first = time.monotonic()
                answer.append(event['text'])
            if event.get('type') == 'error':
                require(False, 'NATIVE_STREAM_ERROR')
            if event.get('type') == 'done':
                done = event
                break
        require(done is not None and first is not None and done.get('saved') is True
                and done.get('s03_integrated') is True and 'маяксевер' in ''.join(answer).casefold(), 'S03_OR_CONTEXT')
        return {'url': origin + '/chat', 'https': True, 'anonymous_protected': True, 'authenticated': True,
                'external_stream_verified': True, 's03_saved': True, 'verified_prior_dialog_context': True,
                'ttft_seconds': round(first - started, 2), 'expires_unix': tunnel['expires_unix']}
    finally:
        conn.close()
