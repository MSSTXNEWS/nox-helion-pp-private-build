#!/usr/bin/env python3
"""Owner-authorized read-only audit of existing new Resonance UI. No model or native write."""

from __future__ import annotations


import argparse


import ast


import contextlib


import fcntl


import hashlib


from html.parser import HTMLParser


import http.cookiejar


import json


import os


from pathlib import Path


import re


import secrets


import signal


import stat


import sys


import threading


import time


import urllib.error


import urllib.request


ROOT = Path('/root/nox')


PROXY = ROOT / 'scripts/chat_proxy.py'


COMMON = PROXY.with_name('common.py')


PROXY_SHA = '7a2f886bd93a4629947b7c8c44b908dc0f0800651b80cb15d0b6818b6cc8b068'


BRIDGE = ROOT / 'scripts/nox_v29_chat_bridge.py'


BRIDGE_SHA = 'ffdefe48fe45d797987fedcf76a231418c6c38c31c33ac8f687d99e753687cee'


WRAPPER = ROOT / 'scripts/nox_web29_onehost_18775.py'


WRAPPER_SHA = '7ab86eee77a36a0f933e6221a069d1c5741059022d0f12494fd2a2ab8d48893a'


BASE = 'http://127.0.0.1:18775'


LOCK = ROOT / 'state/owner_maintenance.lock'


class Hold(Exception):
    """Only fixed public error codes; never raw HTTP/source/OS exceptions."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.]{0,159}', value) else '[WITHHELD]'


def _call_name(node):
    if isinstance(node, ast.Name):
        return _identifier(node.id)
    if isinstance(node, ast.Attribute):
        return _identifier(_call_name(node.value) + '.' + node.attr)
    return '[COMPUTED]'


def regular_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise Hold('HOLD_FILE_TYPE_OR_LIMIT')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            value = stream.read(limit + 1)
        if len(value) > limit:
            raise Hold('HOLD_FILE_LIMIT')
        return value
    finally:
        os.close(fd)


def stable_common_read(path=COMMON):
    """Read existing sibling source as data, with a stable owner-controlled pin."""
    if path.resolve() != path:
        raise Hold('HOLD_COMMON_SOURCE_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_mode & 0o022 or before.st_size > 250000:
            raise Hold('HOLD_COMMON_SOURCE_TYPE_OWNER_OR_SIZE')
        raw = os.pread(fd, 250001, 0)
        after, current = os.fstat(fd), path.lstat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if len(raw) != before.st_size or any(getattr(before, k) != getattr(after, k) or getattr(before, k) != getattr(current, k) for k in fields):
            raise Hold('HOLD_COMMON_SOURCE_CHANGED')
        return raw, {'sha256': digest(raw), 'bytes': len(raw), 'stable_file_identity_verified': True,
                     'binding': 'PINNED_PROXY_FROM_COMMON_IMPORT_SECRETS_FIXED_SIBLING',
                     'code_executed': False, 'loaded_module_memory_identity_verified': False}
    finally:
        os.close(fd)


def exact_common_import(tree):
    rows = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname == 'SECRETS' or alias.name == 'SECRETS' and alias.asname is None:
                    rows.append((node, alias))
    if not rows:
        return False
    if len(rows) != 1 or rows[0][0].module != 'common' or rows[0][0].level != 0 or rows[0][1].name != 'SECRETS' or rows[0][1].asname is not None:
        raise Hold('HOLD_SECRETS_IMPORT_UNSUPPORTED')
    return True


def resolve_password_path(source, source_path=PROXY, allowed_root=ROOT, *, common_source=None):
    """Interpret a tiny path AST grammar; no eval/exec/import or env expansion."""
    tree = ast.parse(source)
    def assignments(unit):
        result = {}
        for node in unit.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        result.setdefault(target.id, []).append(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                result.setdefault(node.target.id, []).append(node.value)
        return result
    assigned = {'proxy': assignments(tree)}
    common_import = exact_common_import(tree)
    if common_import and 'SECRETS' in assigned['proxy']:
        raise Hold('HOLD_DUPLICATE_SECRETS_BINDING')
    if common_source is not None:
        if not common_import:
            raise Hold('HOLD_UNREQUESTED_COMMON_SOURCE')
        assigned['common'] = assignments(ast.parse(common_source))
    readers = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == '_read_chat_password']
    if len(readers) != 1:
        raise Hold('HOLD_AUTH_READER_MISSING')
    body = [n for n in readers[0].body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    # Actual native helper has precisely an OSError -> empty-string fallback.
    if len(body) == 1 and isinstance(body[0], ast.Try):
        attempt = body[0]
        valid = (len(attempt.handlers) == 1 and not attempt.orelse and not attempt.finalbody)
        handler = attempt.handlers[0] if valid else None
        valid = (valid and isinstance(handler.type, ast.Name) and handler.type.id == 'OSError'
                 and handler.name is None and len(handler.body) == 1
                 and isinstance(handler.body[0], ast.Return) and isinstance(handler.body[0].value, ast.Constant)
                 and handler.body[0].value.value == '')
        if not valid:
            raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
        body = attempt.body
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    value = body[0].value
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == 'strip' and not value.args and not value.keywords):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    read = value.func.value
    if not (isinstance(read, ast.Call) and isinstance(read.func, ast.Attribute) and read.func.attr == 'read_text' and isinstance(read.func.value, ast.Name) and read.func.value.id == 'CHAT_PASSWORD_PATH' and not read.args):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    for kw in read.keywords:
        if kw.arg != 'encoding' or not isinstance(kw.value, ast.Constant) or kw.value.value not in ('utf-8', 'utf8'):
            raise Hold('HOLD_AUTH_READER_ENCODING')
    resolving = set()
    dependencies = set()
    def evaluate(node, unit='proxy'):
        if isinstance(node, ast.Name):
            dependencies.add(node.id)
            if len(dependencies) > 64:
                raise Hold('HOLD_PATH_CHAIN_LIMIT')
            identity = (unit, node.id)
            if identity in resolving:
                raise Hold('HOLD_PATH_CYCLE')
            resolving.add(identity)
            if unit == 'proxy' and node.id == 'SECRETS' and common_import:
                if 'common' not in assigned:
                    raise Hold('HOLD_COMMON_SOURCE_REQUIRED')
                result = evaluate(ast.Name(id='SECRETS'), 'common')
                resolving.remove(identity)
                return result
            local = assigned[unit]
            if node.id not in local:
                raise Hold('HOLD_PATH_NAME')
            if len(local[node.id]) != 1:
                raise Hold('HOLD_DUPLICATE_PATH_BINDING')
            result = evaluate(local[node.id][0], unit)
            resolving.remove(identity)
            return result
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path' and len(node.args) == 1 and not node.keywords:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return Path(arg.value)
            if isinstance(arg, ast.Name) and arg.id == '__file__':
                return Path(source_path) if unit == 'proxy' else Path(source_path).with_name('common.py')
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            rhs = node.right
            if isinstance(rhs, ast.Constant) and isinstance(rhs.value, str) and rhs.value and not Path(rhs.value).is_absolute() and '..' not in Path(rhs.value).parts:
                return evaluate(node.left, unit) / rhs.value
        # Exact Path(__file__).resolve().parents[1], interpreted statically.
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == 'parents':
            idx = node.slice
            call = node.value.value
            if isinstance(idx, ast.Constant) and idx.value == 1 and isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'resolve' and not call.args and not call.keywords:
                inner = call.func.value
                if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == 'Path' and len(inner.args) == 1 and isinstance(inner.args[0], ast.Name) and inner.args[0].id == '__file__' and not inner.keywords):
                    unit_path = Path(source_path) if unit == 'proxy' else Path(source_path).with_name('common.py')
                    return unit_path.absolute().parents[1]
        raise Hold('HOLD_PATH_EXPRESSION')
    try:
        result = evaluate(ast.Name(id='CHAT_PASSWORD_PATH'))
        root = Path(allowed_root).absolute()
        if not result.is_absolute() or '..' in result.parts or result == root or root not in result.parents or result.resolve() != result:
            raise Hold('HOLD_AUTH_PATH_OUTSIDE_ROOT_OR_SYMLINK')
    except Hold as exc:
        # Identifiers only. Never source, evaluated values, paths or secret text.
        exc.dependency_identifiers = sorted(name for name in dependencies if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,95}', name))[:32]
        raise
    return result


def scoped_stop_supported(source):
    """Prove the pinned handler only sets the event selected by scope(request)."""
    tree = ast.parse(source)
    registrations = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'register_native_v29_chat']
    if len(registrations) != 1:
        return False
    handlers = [n for n in ast.walk(registrations[0]) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'stream_stop']
    if len(handlers) != 1:
        return False
    nodes = list(ast.walk(handlers[0]))
    key_names = set()
    event_names = set()
    for node in nodes:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            fn = call.func.id if isinstance(call.func, ast.Name) else ''
            if 'scope' in fn.lower() and len(call.args) == 1 and isinstance(call.args[0], ast.Name) and call.args[0].id == 'request':
                key_names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    def keyed_event(node):
        if isinstance(node, ast.Subscript):
            return isinstance(node.value, ast.Name) and 'active' in node.value.id.lower() and isinstance(node.slice, ast.Name) and node.slice.id in key_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get' and isinstance(node.func.value, ast.Name) and 'active' in node.func.value.id.lower() and node.args:
            return isinstance(node.args[0], ast.Name) and node.args[0].id in key_names
        return False
    for node in nodes:
        if isinstance(node, ast.Assign) and keyed_event(node.value):
            event_names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    setters = [node for node in nodes if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'set']
    return bool(key_names and setters and all(not n.args and not n.keywords and (keyed_event(n.func.value) or isinstance(n.func.value, ast.Name) and n.func.value.id in event_names) for n in setters))


@contextlib.contextmanager
def maintenance_lease(borrowed_fd=None):
    owned = borrowed_fd is None
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW) if owned else borrowed_fd
    try:
        actual, expected = os.fstat(fd), os.lstat(LOCK)
        if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise Hold('HOLD_MAINTENANCE_FD_BINDING')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold('HOLD_MAINTENANCE_BUSY') from None
        yield
    finally:
        if owned:
            os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Hold('HOLD_HTTP_REDIRECT')


# This fragment is assembled with exact reviewed helpers into owner_native_audit.py.
from urllib.parse import urlsplit, urljoin, parse_qsl, urlencode

PAGE = '/nox-web-v29/chat.html'
CHAT_ALIAS = '/nox/chat'  # Confirmed existing V13 navigation contract; not a discovered API.
PREFIX = '/nox-web-v29/'
MAX_JS = 24
FILE_LIMIT = 262144
TOTAL_LIMIT = 6 * 1024 * 1024
AUDIT_SECONDS = 90
CRITICAL_JS = ('native-owner.js','workspace.js','nox-connection-v13.js','nox-ui.js','nox-chat.js')
FLAG_CONSUMERS = CRITICAL_JS[1:]
KNOWN_ROUTES = ('/api/nox/chat/stream','/api/nox/chat','/api/nox/stop','/api/nox/status',
                '/api/ui/memory/dialogs/status','/api/ui/memory/dialogs/history',
                '/api/ui/memory/dialogs/create','/api/ui/capabilities',
                '/v1/chat/completions','/completion','/nox/chat')
KNOWN_TITLES = frozenset(('NOX HELION','NOX HELION · РЕЗОНАНС','NOX HELION — Резонанс',
                         'NOX HELION | Резонанс','NOX HELION — CHAT','NOX HELION — Chat'))


def canonical_script_path(value, parent=PAGE):
    """Only observed local script paths; no external origin, traversal or tokens."""
    if not isinstance(value,str) or not 1 <= len(value) <= 400:
        return None
    if any(ord(c) <= 32 for c in value) or any(c in value for c in ('%', '\\', '#')) or value.startswith('//'):
        return None
    while value.startswith('./'):value=value[2:]
    try:raw = urlsplit(value)
    except ValueError:return None
    if raw.scheme or raw.netloc:
        if raw.scheme != 'http' or raw.netloc != '127.0.0.1:18775':
            return None
    if any(part in ('.','..') for part in raw.path.split('/')):
        return None
    try:resolved = urlsplit(urljoin(BASE + parent, value))
    except ValueError:return None
    if resolved.scheme != 'http' or resolved.netloc != '127.0.0.1:18775':
        return None
    path = resolved.path
    if (not path.startswith(PREFIX) or not re.fullmatch(r'/[A-Za-z0-9_./-]{1,240}',path)
            or not path.lower().endswith(('.js','.mjs')) or '//' in path):
        return None
    pairs = parse_qsl(resolved.query, keep_blank_values=True)
    if len(pairs) > 2 or any(k not in ('v','ver','version','rev','hash') or
                             re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',v) is None for k,v in pairs):
        return None
    return path + ('?' + urlencode(pairs) if pairs else '')


def static_identifier(value):
    return (isinstance(value,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',value)
            and not re.search(r'[a-fA-F0-9]{24,}',value))


def wiring(text):
    # Static observations only. No JS executes and no model route is requested.
    lexical=re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|//[^\n]*|/\*[\s\S]*?\*/')
    without_comments=lexical.sub(lambda m:m.group() if m.group()[0] in "\"'`" else ' ',text)
    code_only=lexical.sub(' ',text)
    routes = [route for route in KNOWN_ROUTES if re.search(r'[\'"`]' + re.escape(route) + r'(?:[\'"`?])',without_comments)]
    calls = []
    for route in routes:
        for function in ('fetch','api','apiJSON','post','get'):
            if re.search(r'\b' + function + r'\s*\(\s*[\'"`]' + re.escape(route) + r'[\'"`]',without_comments):
                calls.append({'call':function,'route':route})
    return {'literal_routes':routes,'direct_literal_calls':calls[:30],
            'owner_flag_true_defined':bool(re.search(r'\b(?:window|globalThis)\s*\.\s*NOX_NATIVE_OWNER\s*=\s*true\b',code_only)),
            'owner_flag_gate_present':bool(re.search(r'\bNOX_NATIVE_OWNER\s*===\s*true\b',code_only)),
            'sendNative_definition_present':bool(re.search(r'\b(?:function\s+sendNative\s*\(|(?:const|let|var)\s+sendNative\s*=)',code_only)),
            'model_endpoint_literal_present':any(x in routes for x in ('/v1/chat/completions','/completion')),
            'observation':'STATIC_SOURCE_NOT_EXECUTED'}


class PageProjection(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts=[]; self.dom=[]; self.title=[]; self.inline=[]; self.script_tags=[]
        self.in_title=False; self.in_script=False; self.current=[]; self.script_is_inline=False
        self.discarded_script_refs=0; self.base_tag_present=False; self.script_count=0; self.current_tag=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='base': self.base_tag_present=True
        if tag=='title': self.in_title=True
        if tag=='script':
            self.in_script=True; self.current=[]; self.script_is_inline='src' not in attrs
            self.script_count+=1
            script_type=attrs.get('type','').lower().strip()
            execution='classic' if script_type in ('','text/javascript','application/javascript') else 'module' if script_type=='module' else 'inert'
            self.current_tag={'script_index':self.script_count,'kind':'inline' if self.script_is_inline else 'external',
                              'execution':execution,'async':'async' in attrs,'defer':'defer' in attrs,
                              'owner_flag_true_defined':False}
            if 'src' in attrs:
                path=canonical_script_path(attrs['src'])
                self.current_tag['path']=path if path else '[REJECTED_SCRIPT_REFERENCE]'
                if path and path not in self.scripts: self.scripts.append(path)
                elif not path:self.discarded_script_refs+=1
            if len(self.script_tags)<64:self.script_tags.append(self.current_tag)
        ident=attrs.get('id')
        if static_identifier(ident) and len(self.dom)<160 and re.fullmatch(r'[a-z0-9-]{1,24}',tag):
            row={'tag':tag,'id':ident}
            if tag=='input' and attrs.get('type') in ('text','password','file','checkbox','button','submit','hidden'):
                row['input_type']=attrs['type']
            self.dom.append(row)  # Values, names, text, href and data-* are never copied.
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
        if tag=='script' and self.in_script:
            if self.script_is_inline:
                observed=wiring(''.join(self.current));self.inline.append(observed)
                self.current_tag['owner_flag_true_defined']=observed['owner_flag_true_defined']
            self.in_script=False;self.current=[];self.current_tag=None
    def handle_data(self,data):
        if self.in_title and sum(map(len,self.title))<256:self.title.append(data[:256])
        if self.in_script and self.script_is_inline:self.current.append(data)
    def summary(self,external_wiring=None):
        title=' '.join(''.join(self.title).split())[:256]
        tags=[dict(row) for row in self.script_tags]
        for row in tags:
            if row.get('path') in (external_wiring or {}):
                row['owner_flag_true_defined']=external_wiring[row['path']]['owner_flag_true_defined']
        consumers=[row for row in tags if row.get('path','').split('?',1)[0].rsplit('/',1)[-1] in FLAG_CONSUMERS]
        def before_consumers(row):
            if not consumers or row['execution']!='classic' or row['async'] or not row['owner_flag_true_defined']:
                return False
            # Conservative HTML-order evidence, never a claim that JS executed.
            # Inline classic is parser-blocking even with a meaningless defer attribute.
            blocking=row['kind']=='inline' or not row['defer']
            return all(row['script_index']<consumer['script_index'] and
                       (blocking or consumer['execution']=='classic' and consumer['defer'] and not consumer['async'])
                       for consumer in consumers)
        ordered_flag=self.script_count<=64 and any(before_consumers(row) for row in tags)
        return {'title':title if title in KNOWN_TITLES else '[WITHHELD_UNRECOGNIZED_TITLE]',
                'title_sha256':digest(title.encode()),'dom_ids':self.dom,
                'script_paths':self.scripts[:64],'script_count':len(self.scripts),
                'discarded_script_refs':self.discarded_script_refs,'base_tag_present':self.base_tag_present,
                'inline_wiring':self.inline[:32],
                'script_tag_order':tags,'script_tag_order_truncated':self.script_count>64,
                'owner_flag_true_defined':any(row['owner_flag_true_defined'] for row in tags),
                'owner_flag_before_critical_scripts':ordered_flag,
                'owner_flag_activation_verified':False,
                'source_text_exported':False}


class AuditNoRedirect(NoRedirect):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # Returning None makes urllib raise HTTPError carrying the actual status;
        # no Location is followed or exported, including on official login.
        return None


class AuditHTTP:
    def __init__(self, deadline):
        self.deadline=deadline; self.total=0; self.requests=0; self.allowed_scripts=set()
        self.status_observed=False
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),AuditNoRedirect(),
                                               urllib.request.HTTPCookieProcessor(self.jar))
    def read(self,path,*,password=None):
        allowed=(path in (PAGE,CHAT_ALIAS) or path in self.allowed_scripts and canonical_script_path(path)==path or
                 self.status_observed and path=='/api/nox/status' or
                 password is not None and path=='/chat/login')
        if not allowed or (password is not None and path!='/chat/login'):
            raise Hold('HOLD_AUDIT_ROUTE')
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise Hold('HOLD_AUDIT_DEADLINE')
        body=None if password is None else json.dumps({'password':password}).encode()
        req=urllib.request.Request(BASE+path,data=body,headers={'Accept':'text/html, application/javascript, application/json',
            'Accept-Encoding':'identity','Content-Type':'application/json'})
        self.requests+=1
        try: response=self.opener.open(req,timeout=min(5,remaining))
        except urllib.error.HTTPError as exc:response=exc
        with response:
            limit=min(FILE_LIMIT,TOTAL_LIMIT-self.total)
            if limit<=0:raise Hold('HOLD_AUDIT_TOTAL_BYTES')
            raw=response.read(limit+1);self.total+=len(raw)
            truncated=len(raw)>limit
            encoding=response.headers.get('Content-Encoding','identity').lower()
            mime=response.headers.get('Content-Type','').split(';',1)[0].strip().lower()
            meta={'path':path,'status':int(response.status),'bytes_read':len(raw),
                  'sha256':digest(raw),'sha256_scope':'bounded_prefix' if truncated else 'complete_response',
                  'truncated':truncated,
                  'content_type':mime if mime in ('text/html','text/plain','application/json','application/javascript','text/javascript') else '[OTHER]',
                  'identity_encoding':encoding in ('','identity')}
        return raw if not truncated and encoding in ('','identity') else None,meta


def safe_status(payload):
    if not isinstance(payload,dict):return {'schema_valid':False}
    result={'schema_valid':True}
    value=payload.get('native_p02_bound')
    result['native_p02_bound']=value if type(value) is bool else None
    for key in ('backend','primary_model'):
        value=payload.get(key)
        safe=(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:+/ -]{0,119}',value)
              and not any(x in value.lower() for x in ('secret','password','token','/root/','/home/','://')))
        result[key]=value if safe else '[WITHHELD_OR_UNAVAILABLE]'
    return result


def private_password(path):
    if path.resolve()!=path:raise Hold('HOLD_AUTH_PATH_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid() or before.st_mode&0o077
                or not 6<=before.st_size<=4096):raise Hold('HOLD_CREDENTIAL_FILE_PERMISSIONS')
        raw=os.pread(fd,4097,0);after=os.fstat(fd);current=path.lstat()
        if any(getattr(before,k)!=getattr(after,k) or getattr(before,k)!=getattr(current,k)
               for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):
            raise Hold('HOLD_CREDENTIAL_CHANGED')
        password=raw.decode('utf-8').strip()
        if not 6<=len(password)<=4096:raise Hold('HOLD_CREDENTIAL_UNAVAILABLE')
        return password
    finally:os.close(fd)


def safe_failure_code(exc):
    return str(exc) if isinstance(exc,Hold) and re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}',str(exc)) else 'HOLD_BOUNDED_AUDIT_FAILURE'


def audit(*,expected_source_sha,maintenance_lock_fd=None):
    start=time.monotonic();deadline=start+AUDIT_SECONDS
    request_id=os.environ.get('NOX_OWNER_REQUEST_ID','');source_sha=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch(r'[0-9]{1,24}',request_id) or not re.fullmatch('[a-f0-9]{40}',source_sha) or source_sha!=expected_source_sha:
        raise Hold('HOLD_OWNER_REQUEST_SOURCE_BINDING')
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):
        raise Hold('HOLD_MAIN_THREAD_DEADLINE_REQUIRED')
    report={'schema':'NOX_NEW_RESONANCE_READ_ONLY_AUDIT_V1','owner_request_id':request_id,
            'owner_source_sha':source_sha,'page':PAGE,'model_requests':0,'dialogs_created':0,
            'stop_requests':0,'reloads':0,'native_file_writes':0,'external_requests':0,
            'source_text_exported':False,'credentials_exported':False,'js_executed':False,
            'public_tunnel_verified':False,'native_model_origin_verified':False}
    previous=signal.getsignal(signal.SIGALRM)
    def expired(*_):raise Hold('HOLD_AUDIT_DEADLINE')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,AUDIT_SECONDS)
    client=AuditHTTP(deadline)
    try:
        with maintenance_lease(maintenance_lock_fd):
            sources={}
            for label,path,pin in (('proxy',PROXY,PROXY_SHA),('bridge',BRIDGE,BRIDGE_SHA),('wrapper',WRAPPER,WRAPPER_SHA)):
                raw,identity=stable_common_read(path)
                if identity['sha256']!=pin:raise Hold('HOLD_'+label.upper()+'_SHA_CHANGED')
                sources[label]=raw.decode('utf-8')
            common=None
            if exact_common_import(ast.parse(sources['proxy'])):
                raw,identity=stable_common_read();common=raw.decode('utf-8');report['common_source_pin']=identity
            password_path=resolve_password_path(sources['proxy'],common_source=common)
            report['scoped_cancel_contract_verified']=scoped_stop_supported(sources['bridge'])
            password=private_password(password_path)
            try:_,login=client.read('/chat/login',password=password)
            finally:password=None
            if login['status']!=200 or not any(True for _ in client.jar):raise Hold('HOLD_OFFICIAL_LOGIN_NO_SESSION')
            raw,meta=client.read(PAGE);report['html']=meta
            if raw is None or meta['status']!=200 or meta['content_type']!='text/html':
                report['status']='UI_AUDIT_COMPLETE_PAGE_UNAVAILABLE';return report
            text=raw.decode('utf-8');parser=PageProjection();parser.feed(text);summary=parser.summary()
            report['page_projection']=summary
            report['owner_flag_true_defined']=summary['owner_flag_true_defined']
            report['owner_flag_before_critical_scripts']=summary['owner_flag_before_critical_scripts']
            report['owner_flag_activation_verified']=False
            if parser.base_tag_present:
                report['status']='UI_AUDIT_COMPLETE_BASE_TAG_REQUIRES_REVIEW';return report
            all_wiring=list(parser.inline);rows=[];external_wiring={};report['scripts']=rows
            ordered=sorted(parser.scripts,key=lambda x:(x.split('?',1)[0].rsplit('/',1)[-1] not in CRITICAL_JS,parser.scripts.index(x)))
            client.allowed_scripts.update(ordered[:MAX_JS])
            for path in ordered[:MAX_JS]:
                source,metadata=client.read(path);row=dict(metadata);rows.append(row)
                if source is not None and metadata['status']==200 and metadata['content_type'] in ('application/javascript','text/javascript','text/plain'):
                    observed=wiring(source.decode('utf-8'));row['wiring']=observed;all_wiring.append(observed)
                    external_wiring[path]=observed
                    report['page_projection']=parser.summary(external_wiring)
                    report['owner_flag_true_defined']=report['page_projection']['owner_flag_true_defined']
                    report['owner_flag_before_critical_scripts']=report['page_projection']['owner_flag_before_critical_scripts']
            report['unfetched_script_count']=max(0,len(ordered)-MAX_JS)
            report['owner_flag_true_defined']=any(x['owner_flag_true_defined'] for x in all_wiring)
            routes={v for x in all_wiring for v in x['literal_routes']}
            report['sendNative_definition_present']=any(x['sendNative_definition_present'] for x in all_wiring)
            report['native_stream_literal_present']='/api/nox/chat/stream' in routes
            report['model_endpoint_literal_present']=any(x['model_endpoint_literal_present'] for x in all_wiring)
            if '/api/nox/status' in routes:
                client.status_observed=True;status_raw,status_meta=client.read('/api/nox/status');report['status_route']=status_meta
                if status_raw is not None and status_meta['status']==200 and status_meta['content_type']=='application/json':
                    try:report['status_fields']=safe_status(json.loads(status_raw))
                    except (ValueError,UnicodeError):report['status_fields']={'schema_valid':False}
            alias_raw,alias=client.read(CHAT_ALIAS);report['known_chat_alias']=alias
            alias['route_basis']='FIXED_V13_NAVIGATION_CONTRACT'
            alias['same_body_as_main']=alias_raw is not None and alias['sha256']==meta['sha256']
            report['status']='UI_AUDIT_COMPLETE';return report
    except Exception as exc:
        report['status']=safe_failure_code(exc);report['partial']=True
        return report
    finally:
        report['loopback_requests']=client.requests;report['bytes_read']=client.total
        report['elapsed_ms']=round((time.monotonic()-start)*1000)
        client.jar.clear();signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def main():
    try:
        report=audit(expected_source_sha=os.environ.get('NOX_OWNER_SOURCE_SHA',''))
    except Exception as exc:
        code=safe_failure_code(exc)
        report={'schema':'NOX_NEW_RESONANCE_READ_ONLY_AUDIT_V1','status':code,
                'model_requests':0,'dialogs_created':0,'stop_requests':0,'native_file_writes':0,
                'credentials_exported':False,'source_text_exported':False}
    encoded=json.dumps(report,ensure_ascii=False,separators=(',',':'))
    if len(encoded.encode())>120000:
        report={'schema':'NOX_NEW_RESONANCE_READ_ONLY_AUDIT_V1','status':'HOLD_AUDIT_OUTPUT_LIMIT'}
        encoded=json.dumps(report,separators=(',',':'))
    complete=report['status'].startswith('UI_AUDIT_COMPLETE')
    print('NOX_MAINT_AUDIT='+encoded,flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE='+str(complete).lower(),flush=True)
    return 0 if complete else 2


if __name__=='__main__':raise SystemExit(main())
