"""Mount the paired owner media interface on the exact deployed Resonance edge."""

import ast
from hashlib import sha256


PAGE_BY_EDGE = {
    "4dfc48d178de35c1ba3b6625fd2cd7e2df891b3dac6c515947971e4863a97eeb":
        "a3864e371dd38b0ffbbb11ba23ba8da7615de8e7af320aebe0d2118566880e5f",
    # Output of the reviewed same-origin adviser transform.
    "6697fd91f95d951815ba46f3bc619151499e767c297d8a358cc815aeb03a136e":
        "b4c4270a1b976d2f114725c9a2f1b8853dbd534657a4d32ef3534c3f010b0bc7",
}
SCRIPT_PIN = "c2718756179876b8cd329ccecbe0cda678cc4e4c13535d5f29b3fb755d68ae9d"
STYLE_PIN = "46ed48242750e7eba067398e185e4861882919ff073c93a4e98be8a7f694974a"

CONSTANTS = """
MEDIA = '/api/ui/media'
MEDIA_READ = re.compile(r'/api/ui/media/(?:jobs|requests)/[0-9a-f]{32}')
MEDIA_CANCEL = re.compile(r'/api/ui/media/jobs/[0-9a-f]{32}/cancel')
MEDIA_OUTPUT = re.compile(r'/api/ui/media/jobs/[0-9a-f]{32}/outputs/[0-3]')
MEDIA_RANGE = re.compile(r'bytes=(?:[0-9]{1,9}-[0-9]{0,9}|-[0-9]{1,9})')
MEDIA_OUTPUT_LIMIT = 256 * 1024 * 1024
"""

HANDLER = '''
    def route_media(self, target, host):
        path = target.path
        origin = self.headers.get('Origin')
        if (not PUBLIC_HOST.fullmatch(host) or
                self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin') or
                origin is not None and origin != 'https://' + host):
            self.reply(403)
            return
        if target.query or self.headers.get('Transfer-Encoding'):
            self.reply(400)
            return
        headers = self.upstream_headers(False)
        if 'Cookie' not in headers:
            self.reply(401)
            return
        output = self.command == 'GET' and bool(MEDIA_OUTPUT.fullmatch(path))
        cancel = self.command == 'POST' and bool(MEDIA_CANCEL.fullmatch(path))
        create = self.command == 'POST' and path == MEDIA + '/jobs'
        read = self.command == 'GET' and (path == MEDIA or MEDIA_READ.fullmatch(path))
        if not (output or cancel or create or read):
            self.reply(404)
            return
        body = None
        if create:
            body = self.read_body()
            if body is None or len(body) > 12000:
                self.reply(400)
                return
        else:
            if self.headers.get_all('Content-Length', []) not in ([], ['0']):
                self.reply(400)
                return
            if cancel:
                body = b'{}'
        ranges = self.headers.get_all('Range', [])
        if ranges:
            if not output or len(ranges) != 1 or not MEDIA_RANGE.fullmatch(ranges[0]):
                self.reply(416)
                return
            headers['Range'] = ranges[0]
        if body is not None:
            headers['Content-Type'] = 'application/json'
            headers['Sec-Fetch-Site'] = 'same-origin'
        upstream = http.client.HTTPConnection(*PROXY, timeout=15)
        sent = False
        try:
            upstream.request(self.command, path, body=body, headers=headers)
            response = upstream.getresponse()
            status = response.status
            content_type = response.getheader('Content-Type', '').split(';', 1)[0].strip().lower()
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                self.reply(502)
                return
            if output and status in (200, 206):
                lengths = response.headers.get_all('Content-Length', [])
                if (content_type not in ('image/png', 'video/webm') or len(lengths) != 1
                        or not re.fullmatch(r'[0-9]{1,9}', lengths[0])
                        or not 0 < int(lengths[0]) <= MEDIA_OUTPUT_LIMIT):
                    self.reply(502)
                    return
                size = int(lengths[0])
                content_range = response.getheader('Content-Range')
                if status == 206:
                    match = re.fullmatch(r'bytes ([0-9]{1,9})-([0-9]{1,9})/([0-9]{1,9})',
                                         content_range or '')
                    if not ranges or not match:
                        self.reply(502)
                        return
                    first, last, total = map(int, match.groups())
                    if not (0 <= first <= last < total <= MEDIA_OUTPUT_LIMIT and last - first + 1 == size):
                        self.reply(502)
                        return
                elif content_range is not None:
                    self.reply(502)
                    return
                self.send_response(status)
                self.headers_no_cache()
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(size))
                self.send_header('Accept-Ranges', 'bytes')
                if content_range is not None:
                    self.send_header('Content-Range', content_range)
                sent = True
                self.end_headers()
                while size:
                    chunk = response.read(min(size, 65536))
                    if not chunk:
                        return
                    self.wfile.write(chunk)
                    size -= len(chunk)
                return
            if status in (401, 403, 416) and content_type != 'application/json':
                self.reply(status)
                return
            if (status not in (200, 202, 400, 401, 403, 404, 409, 415, 416, 422, 429, 503)
                    or output and status in (200, 202) or content_type != 'application/json'):
                self.reply(502)
                return
            raw = response.read(65537)
            if len(raw) > 65536 or not isinstance(json.loads(raw), dict):
                self.reply(502)
                return
            self.reply(status, raw)
        except (OSError, http.client.HTTPException, ValueError, RecursionError):
            if not sent:
                self.reply(502)
        finally:
            upstream.close()

'''


def replace_once(source, anchor, value):
    if source.count(anchor) != 1:
        raise ValueError("HOLD_MEDIA_EDGE_ANCHOR")
    return source.replace(anchor, value, 1)


def attach_media_edge(edge: bytes, script: bytes, style: bytes) -> bytes:
    """Return one exact source candidate with all media assets embedded locally."""
    expected_page = PAGE_BY_EDGE.get(sha256(edge).hexdigest())
    if expected_page is None or (sha256(script).hexdigest(), sha256(style).hexdigest()) != (SCRIPT_PIN, STYLE_PIN):
        raise ValueError("HOLD_MEDIA_EDGE_SOURCE_PINS")
    source, js, css = (raw.decode("utf-8") for raw in (edge, script, style))
    assignment = next(node for node in ast.parse(source).body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "PAGE" for target in node.targets))
    page = assignment.value.func.value.value
    if sha256(page.encode()).hexdigest() != expected_page:
        raise ValueError("HOLD_MEDIA_EDGE_PAGE_PIN")
    for old, new in (("chatForm", "send"), ("prompt", "question"), ("messages", "history")):
        js = replace_once(js, "getElementById(" + repr(old) + ")", "getElementById(" + repr(new) + ")")
    if "</script" in js.casefold() or "</style" in css.casefold() or "'''" in js + css:
        raise ValueError("HOLD_MEDIA_EDGE_ASSET_BOUNDARY")
    mounted = replace_once(page, "</style><main>", css + "\n</style><main>")
    mounted = replace_once(mounted, "</script></html>", "</script><script>\n" + js + "</script></html>")
    source = replace_once(source, "PAGE = r'''" + page + "'''.encode()",
                          "PAGE = " + repr(mounted.encode()))
    source = replace_once(source, "TURN = '/api/nox/chat/turn'\n", "TURN = '/api/nox/chat/turn'\n" + CONSTANTS)
    guard = "        if target.path in (TURN, STOP):"
    source = replace_once(source, guard, """        if target.path == MEDIA or target.path.startswith(MEDIA + '/'):
            self.route_media(target, host)
            return
""" + guard)
    source = replace_once(source, "    def read_body(self):", HANDLER + "    def read_body(self):")
    anchor = "connect-src 'self'; form-action 'self';"
    source = replace_once(source, anchor, "connect-src 'self'; img-src 'self'; media-src 'self'; form-action 'self';")
    candidate = source.encode("utf-8")
    compile(candidate, "owner_resonance_gateway.py", "exec")
    return candidate
