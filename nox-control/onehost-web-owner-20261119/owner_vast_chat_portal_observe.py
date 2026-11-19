"""Read only the current Vast portal routes for the native NOX chat."""

import http.client
from ipaddress import ip_address
import json
import os
import re
from urllib.parse import urlsplit


INSTANCE = '60509551'
CHAT_PORTS = {8080, 18775}
MAX_BODY = 192 * 1024
LOCAL = '127.0.0.1'
TOKEN_PATHS = frozenset(('', '/', '/chat', '/chat/', '/nox-web-v29', '/nox-web-v29/',
                         '/nox-web-v29/pc/resonance.html'))
SERVICE_NAMES = frozenset(('nox', 'nox helion', 'nox-proxy', 'nox-web29-18775',
                           'nox chat', 'nox helion web', 'nox helion chat', 'nox web29'))
INTERNAL_PORT_FIELDS = frozenset(('internal_port', 'local_port', 'target_port', 'container_port',
                                  'backend_port', 'service_port'))
LOCAL_URL_FIELDS = frozenset(('internal_url', 'local_url', 'target_url', 'service_url', 'origin_url',
                              'backend_url', 'local', 'target', 'upstream', 'origin'))
HOST = re.compile(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'
                  r'[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?', re.I)


def observe(port, path, limit=0):
    conn = http.client.HTTPConnection(LOCAL, port, timeout=2)
    try:
        conn.request('GET', path, headers={'Accept': 'application/json', 'Connection': 'close'})
        response = conn.getresponse()
        body = response.read(limit + 1) if limit and response.status == 200 else None
        return response.status, body if body is not None and len(body) <= limit else None
    except (OSError, http.client.HTTPException):
        return None, None
    finally:
        conn.close()


def key(value):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', value).lower().replace('-', '_')


def likely_service(row, inherited_name):
    for field, value in row.items():
        field = key(field)
        if field in INTERNAL_PORT_FIELDS:
            if type(value) is int and value in CHAT_PORTS or type(value) is str and value in ('8080', '18775'):
                return True
        if field in LOCAL_URL_FIELDS and isinstance(value, str) and len(value) < 300:
            try:
                url = urlsplit(value)
                if url.hostname in (LOCAL, 'localhost', '::1') and url.port in CHAT_PORTS:
                    return True
            except ValueError:
                continue
        if field in ('name', 'title', 'label', 'service_name', 'id') and isinstance(value, str):
            if value.strip().casefold() in SERVICE_NAMES:
                return True
    return inherited_name.strip().casefold() in SERVICE_NAMES


def public_https(value):
    if not isinstance(value, str) or not value.startswith('https://') or len(value) > 768:
        return None
    try:
        url = urlsplit(value)
        host = url.hostname
        if not host or url.username is not None or url.password is not None or url.path not in TOKEN_PATHS:
            return None
        try:
            ip = ip_address(host)
        except ValueError:
            if not HOST.fullmatch(host) or host.endswith(('.local', '.localhost', '.internal', '.test', '.invalid')):
                return None
            if re.fullmatch(r'[0-9a-f]{24,}', host.split('.')[0]):
                return None
            authority = host
        else:
            if not ip.is_global:
                return None
            authority = f'[{ip}]' if ip.version == 6 else str(ip)
        port = url.port
        if port is not None and port != 443:
            authority += ':' + str(port)
        return {'url': 'https://' + authority + '/chat',
                'quick_tunnel': host.endswith('.trycloudflare.com')}
    except ValueError:
        return None


def advertised_urls(document):
    candidates = {}

    def visit(value, field='', bound=False, depth=0):
        if depth > 8 or len(candidates) >= 12:
            return
        if isinstance(value, dict):
            bound = bound or likely_service(value, field)
            for name, child in value.items():
                if isinstance(child, (dict, list)) or bound and ('url' in key(name) or key(name) in ('https', 'tunnel', 'external', 'public')):
                    visit(child, name, bound, depth + 1)
        elif isinstance(value, list):
            for child in value[:80]:
                visit(child, field, bound, depth + 1)
        elif bound:
            row = public_https(value)
            if row is not None:
                candidates[row['url']] = row

    visit(document)
    return list(candidates.values())


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    labels = {os.environ[name].removeprefix('C.') for name in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(name)}
    if (os.geteuid() != 0 or labels != {INSTANCE} or not re.fullmatch(r'[1-9][0-9]{0,19}', request)
            or not re.fullmatch(r'[a-f0-9]{40}', source)):
        print('NOX_MAINT_CHAT_PORTAL_HOLD=OWNER_INSTANCE_BINDING', flush=True)
        return 2

    status, raw = observe(11111, '/capabilities/services', MAX_BODY)
    try:
        portal = json.loads(raw) if raw is not None else None
    except (ValueError, RecursionError):
        portal = None
    backends = {str(port): {'chat_http': observe(port, '/chat')[0],
                           'unauthenticated_status_http': observe(port, '/api/nox/status')[0]}
                for port in sorted(CHAT_PORTS)}
    receipt = {'request': request, 'source_sha': source, 'instance': int(INSTANCE),
               'portal_status_http': status, 'portal_response_parsed': isinstance(portal, (dict, list)),
               'portal_advertised_https': advertised_urls(portal), 'native_backends': backends,
               'external_transport_verified': False}
    print('NOX_MAINT_CHAT_PORTAL_ROUTES=' + json.dumps(receipt, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
