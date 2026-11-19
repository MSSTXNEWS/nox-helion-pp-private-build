"""Bind one normal-motion QA turn to its actually loaded public V135 response.

This private overlay adds no request, route, production change or model action.
The fixed URL comes from pinned owner_chat_ui.decorate_html (da2cea21...), not
from a guessed static path. A separate HTTP GET is never acceptance evidence.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import urllib.parse

NORMAL_SHA = 'd7b0c58bec74f87215725c541d530317df35d6c6ef448b2f0f713ba7778a0b71'
ASSET_PATH = '/nox-web-v29/nox-v135-resonance-owner-bridge.js'
ASSET_SHA = '02d6a0fe1d67dd6d19c020d9cb7540611b1c5ed1dbefa304e483277d140ebffc'
ASSET_BYTES = 20171
SCHEMA = 'NOX_BROWSER_LOADED_ASSET_BINDING_V1'
SCOPE = 'NORMAL_TOKEN_SPANS_AND_LOADED_V135_IDENTITY_ONLY'
BODY_TIMEOUT = 3.0
WIRE_LIMIT = 64 * 1024
ENCODINGS = frozenset(('identity', 'gzip', 'br', 'deflate'))


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_NORMAL_ASSET_' + code)


def initial_binding():
    return {'schema': SCHEMA, 'scope': SCOPE, 'path': ASSET_PATH,
        'expected_sha256': ASSET_SHA, 'expected_bytes': ASSET_BYTES,
        'state': 'WAITING_FOR_PAGE_SCRIPT_RESPONSE', 'response_count': 0,
        'body_read_count': 0, 'verified_before_submit': False, 'verified_at_finish': False,
        'body_verified': False, 'listener_closed': False,
        'wire_size_source': 'PLAYWRIGHT_REQUEST_SIZES_RESPONSE_BODY_SIZE',
        'wire_size_bounded': False,
        'separate_asset_request_issued': False, 'raw_body_or_headers_exported': False}


def complete(value):
    return bool(isinstance(value, dict) and value.get('schema') == SCHEMA
        and value.get('scope') == SCOPE and value.get('path') == ASSET_PATH
        and value.get('expected_sha256') == value.get('body_sha256') == ASSET_SHA
        and type(value.get('expected_bytes')) is int and value['expected_bytes'] == ASSET_BYTES
        and type(value.get('body_bytes')) is int and value['body_bytes'] == ASSET_BYTES
        and type(value.get('response_count')) is int and value['response_count'] == 1
        and type(value.get('body_read_count')) is int and value['body_read_count'] == 1
        and type(value.get('http_status')) is int and value['http_status'] == 200
        and value.get('content_encoding') in ENCODINGS
        and type(value.get('browser_reported_wire_bytes')) is int
        and 0 < value['browser_reported_wire_bytes'] <= WIRE_LIMIT
        and value.get('state') == 'VERIFIED'
        and all(value.get(key) is True for key in ('same_origin', 'exact_request_url',
            'get_method', 'script_resource', 'main_frame', 'no_redirect',
            'service_worker_absent', 'known_content_encoding', 'wire_length_header_valid',
            'wire_size_bounded',
            'body_verified', 'verified_before_submit', 'verified_at_finish', 'listener_closed'))
        and value.get('separate_asset_request_issued') is False
        and value.get('raw_body_or_headers_exported') is False)


class LoadedAsset:
    """Listen only to the page's fixed script; at most one bounded body read."""

    def __init__(self, core, page, report, base):
        parsed = urllib.parse.urlsplit(base)
        require(parsed.scheme in ('http', 'https') and parsed.hostname
            and not parsed.username and not parsed.password
            and parsed.path in ('', '/') and not parsed.query and not parsed.fragment, 'BASE_ORIGIN')
        self.core, self.page = core, page
        self.origin = (parsed.scheme, parsed.netloc)
        self.url = urllib.parse.urlunsplit((*self.origin, ASSET_PATH, '', ''))
        self.row = report['asset_binding']
        self.response = self.task = None
        self.callback = self.on_response
        page.on('response', self.callback)

    def hold(self, reason):
        self.row.update(state='HELD', reason='HOLD_NORMAL_ASSET_' + reason,
            verified_at_finish=False)

    def on_response(self, response):
        try:
            parsed = urllib.parse.urlsplit(response.url)
            if parsed.path != ASSET_PATH:
                return
            self.row['response_count'] = min(2, self.row['response_count'] + 1)
            if self.row['response_count'] != 1:
                self.hold('DUPLICATE_RESPONSE'); return
            request = response.request
            headers = response.headers
            length = headers.get('content-length')
            encoding = headers.get('content-encoding', 'identity').lower().strip()
            valid_length = (length is None or isinstance(length, str) and length.isascii()
                and 0 < len(length) <= 8 and length.isdecimal() and 0 < int(length) <= WIRE_LIMIT)
            declared = int(length) if length is not None and valid_length else None
            metadata = {'same_origin': (parsed.scheme, parsed.netloc) == self.origin,
                'exact_request_url': response.url == request.url == self.url,
                'get_method': request.method == 'GET',
                'script_resource': request.resource_type == 'script',
                'main_frame': request.frame is self.page.main_frame,
                'no_redirect': request.redirected_from is None and request.redirected_to is None,
                'service_worker_absent': response.from_service_worker is False,
                'known_content_encoding': encoding in ENCODINGS,
                'wire_length_header_valid': valid_length}
            self.row.update(metadata, http_status=response.status if type(response.status) is int else None,
                content_encoding=encoding if encoding in ENCODINGS else 'UNSUPPORTED',
                declared_wire_bytes=declared, wire_length_header_present=length is not None)
            if response.status != 200 or type(response.status) is not int or not all(metadata.values()):
                self.hold('RESPONSE_METADATA'); return
            if self.row.get('state') == 'HELD':
                return
            self.response = response
            self.row['state'] = 'READING_PAGE_SCRIPT_RESPONSE'
            self.task = asyncio.create_task(self.read_body(response))
        except Exception:
            self.hold('RESPONSE_METADATA_UNAVAILABLE')

    async def read_body(self, response):
        async def bounded_response():
            # Request.sizes is passive browser metadata, not another HTTP fetch.
            # Its responseBodySize describes encoded bytes (and may fall back
            # to Content-Length). Unknown/zero/oversized values cannot admit a
            # body read. Browser-decoded bytes get their own exact length+SHA.
            await response.finished()
            sizes = await response.request.sizes()
            wire = sizes.get('responseBodySize') if isinstance(sizes, dict) else None
            if type(wire) is not int or not 0 < wire <= WIRE_LIMIT:
                self.hold('WIRE_SIZE_UNKNOWN_OR_UNBOUNDED'); return None
            self.row['browser_reported_wire_bytes'] = wire
            declared = self.row.get('declared_wire_bytes')
            if declared is not None and wire != declared:
                self.hold('WIRE_SIZE_MISMATCH'); return None
            self.row['wire_size_bounded'] = True
            if self.core.stop_present():
                self.hold('OWNER_STOP'); return None
            self.row['body_read_count'] += 1
            return await response.body()

        try:
            if self.core.stop_present():
                self.hold('OWNER_STOP'); return
            raw = await asyncio.wait_for(bounded_response(), timeout=BODY_TIMEOUT)
            if self.row.get('state') == 'HELD':
                return
            if self.core.stop_present():
                self.hold('OWNER_STOP'); return
            if not isinstance(raw, bytes) or len(raw) != ASSET_BYTES:
                self.hold('BODY_LENGTH'); return
            self.row.update(body_bytes=len(raw), body_sha256=hashlib.sha256(raw).hexdigest())
            if self.row['body_sha256'] != ASSET_SHA:
                self.hold('BODY_PIN'); return
            if self.row.get('state') != 'HELD':
                self.row.update(state='BODY_VERIFIED', body_verified=True)
        except asyncio.CancelledError:
            if self.row.get('state') != 'HELD':
                self.hold('BODY_CANCELLED')
            raise
        except TimeoutError:
            self.hold('BODY_TIMEOUT')
        except Exception:
            self.hold('BODY_READ')

    async def verify(self, phase):
        require(phase in ('BEFORE_POST', 'FINAL'), 'PHASE')
        if self.core.stop_present():
            raise RuntimeError('HOLD_OWNER_STOP')
        if self.task is not None:
            await asyncio.shield(self.task)
        if self.core.stop_present():
            raise RuntimeError('HOLD_OWNER_STOP')
        if self.row.get('state') == 'HELD':
            raise RuntimeError(self.row['reason'])
        require(self.row['response_count'] == 1 and self.row['body_read_count'] == 1
            and self.row.get('body_verified') is True, 'PAGE_SCRIPT_RESPONSE_MISSING')
        if phase == 'BEFORE_POST':
            self.row['verified_before_submit'] = True
        else:
            require(self.row['verified_before_submit'] is True, 'SUBMIT_BINDING_MISSING')
            self.row.update(verified_at_finish=True, state='VERIFIED')

    async def close(self):
        self.page.remove_listener('response', self.callback)
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.row['listener_closed'] = True


def rewrite_browser(source):
    """Four exact AST seams; all existing auth/POST/stream/S03 checks survive."""
    tree = ast.parse(source)
    require(len(tree.body) == 1 and isinstance(tree.body[0], ast.AsyncFunctionDef)
        and tree.body[0].name == 'browser_run', 'BROWSER_FUNCTION')
    matches = {key: 0 for key in ('page', 'submit', 'final', 'close')}
    key = lambda node: ast.dump(node, include_attributes=False)
    page_key = key(ast.parse('page = await context.new_page()').body[0])
    submit_key = key(ast.parse("report['resources_at_submit'] = budget()").body[0])
    final_key = key(ast.parse('public != EXPECTED', mode='eval').body)
    close_key = key(ast.parse('await context.close()').body[0])

    class Bind(ast.NodeTransformer):
        def visit_Assign(self, node):
            original = key(node); node = self.generic_visit(node)
            if original == page_key:
                matches['page'] += 1
                return [node, ast.parse('asset_probe = _nox_loaded_asset(page, report, base)').body[0]]
            if original == submit_key:
                matches['submit'] += 1
                return [ast.parse("await asset_probe.verify('BEFORE_POST')").body[0], node]
            return node

        def visit_If(self, node):
            original = key(node.test); node = self.generic_visit(node)
            if original == final_key:
                matches['final'] += 1
                return [node, ast.parse("await asset_probe.verify('FINAL')").body[0]]
            return node

        def visit_Expr(self, node):
            original = key(node); node = self.generic_visit(node)
            if original == close_key:
                matches['close'] += 1
                return [ast.parse('if asset_probe is not None:\n await asset_probe.close()').body[0], node]
            return node

    tree = Bind().visit(tree)
    require(all(count == 1 for count in matches.values()), 'BROWSER_ANCHOR')
    tree.body[0].body.insert(0, ast.parse('asset_probe = None').body[0])
    ast.fix_missing_locations(tree)
    value = ast.unparse(tree)
    compile(value, '<loaded-asset-normal-motion>', 'exec')
    return value


def install(core, raw, transport, traw, release, rraw, scope, sraw, normal, nraw):
    require(hashlib.sha256(nraw).hexdigest() == NORMAL_SHA, 'NORMAL_SOURCE_PIN')
    original_gate = core.progressive_stream_valid
    original_rewrite = normal.rewrite_browser
    normal.rewrite_browser = lambda body: rewrite_browser(original_rewrite(body))
    normal.install(core, raw, transport, traw, release, rraw, scope, sraw)
    require(core.progressive_stream_valid is original_gate, 'STRICT_GATE_CHANGED')
    core._nox_loaded_asset = lambda page, report, base: LoadedAsset(core, page, report, base)
    original_browser = core.browser_run

    async def browser_run(report, directory, available):
        report.update(asset_binding=initial_binding(), asset_identity_verified=False,
            asset_identity_scope=SCOPE)
        await original_browser(report, directory, available)
        require(complete(report.get('asset_binding')), 'FINAL_BINDING_INCOMPLETE')
        report['asset_identity_verified'] = True

    core.browser_run = browser_run
    return core
