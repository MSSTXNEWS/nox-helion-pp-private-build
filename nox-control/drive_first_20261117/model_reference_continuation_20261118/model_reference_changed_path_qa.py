"""One proven-zero-send continuation in the already-owned QA dialog.

The two prior messages stay private and must remain byte-for-byte unchanged.
No dialog creation, app imports, source edits, service mutation, counter reset,
external HTTP or automatic retry. Only the new synthetic answer may be returned.
"""
from __future__ import annotations

import ast
import contextlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import threading
import time
import urllib.request

import p0_native_helpers as native
from p0_witness_protocol import Hold, require, digest, read_v24
from model_reference_qa_release import RELEASE
from p0_login_idle_wait import LoginIdleWait, evidence_read, ARBITER_SHA

BASE = 'http://127.0.0.1:18775'
DIALOG = '12092579cf5144419cfa4fadc2e3a03b'
OLD_EXCHANGE = 'S03-48140046c4684fe5'
OLD_RECORD_SHA = 'b7513f8177f4ec65b9dd65f248097108bf4e2a2cb364e407e3cb191f98e4bdec'
QUESTION = 'Какая модель в твоей основе сейчас?'
MODEL_REFERENCE = 'DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf'
HISTORY_PATH = '/api/ui/memory/dialogs/history?dialog_id=' + DIALOG + '&limit=4'
MENU_PATH = '/nox-web-v29/nox-ui.js'
MENU_SHA = '13897495d7c9c628ef4f3094fafdad5f5932a3570d21c650112ba7138ab3c2f0'
DB = native.ROOT / 'kb/knowledge.sqlite'
JOURNAL = 'owner_model_reference_acceptance_20261118'
MAX_WALL = 420.0
MAX_RECEIPT = 65536
PRIOR_REQUEST = '6964382138'
PRIOR_SOURCE = '6dd20a0aac59742138918840c3b4bb1963142928'
PRIOR_OUTCOME_SHA = 'f0224c15acf37aaad4b45380ce174a27ae2acbafbdf361f036f07eca846e4fd9'
PRIOR_OUTCOME_BYTES = 3534
PRIOR_PREFIX_SHA = '2abccd3b98bc45ee14c384c8866f9b55ab797b34233c38537512af43e45eb5e0'
CONTINUATION = 'continuation_6964382138'
COUNTER = native.ROOT / 'status/chat_state.json'
MAX_COUNTER_BYTES = 4096
SOURCE_PINS = {
    'chat_proxy.py': '30207a85eed6c87df4a6ee4dd8614442a62622eefacac7fae822b23ad385b343',
    'owner_chat_stream.py': '38f4dc2995dd2c31f1f4d6a816d485721267d7add1c789cc4693aca54233fe09',
    'nox_v29_chat_bridge.py': '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a',
    'owner_model_reference_binding.py': 'b9f4addc252c8a0339e2123680fe5a0ab47cef15e725ecec0747f5934a2759ad',
    'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
    'agent_loop.py': '0ecec93bcf3239b7decc768862d27fbdc60fe2b613103f201406761bb4850aaa',
    's03_memory.py': '776a6dc25726540d75ec51216d1e333ca89b24e803ba3620f9b5e470a3c81476',
    'nox_web29_onehost_18775.py': '7ab86eee77a36a0f933e6221a069d1c5741059022d0f12494fd2a2ab8d48893a',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'HOLD_DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(Hold('HOLD_NONFINITE_JSON')))
    except (ValueError, UnicodeError, RecursionError):
        raise Hold('HOLD_JSON_SCHEMA') from None


def body(nonce):
    require(isinstance(nonce, str) and re.fullmatch('[a-f0-9]{32}', nonce), 'HOLD_NONCE')
    # The exact question is a full-match identity route. A tag in its text would
    # exercise the generic route, so the nonce belongs only in request metadata.
    return {'message': QUESTION, 'history': [], 'dialog_id': DIALOG,
            'request_id': 'model-reference-' + nonce, 'max_tokens': 256}


def runtime_projection(identity):
    row = identity.get('process')
    require(isinstance(row, dict), 'HOLD_PROXY_PROCESS_MISSING')
    return {name: row.get(name) for name in RELEASE['runtime_identity']}


def installed_release(identity):
    require(runtime_projection(identity) == RELEASE['runtime_identity'], 'HOLD_ACTUAL_PROXY_GENERATION')
    config = identity['config']
    require(config['sha256'] == RELEASE['config_sha256']
            and config.get('launcher_sha256') == RELEASE['launcher_sha256']
            and digest(config['values']['command'].encode()) == RELEASE['command_sha256'],
            'HOLD_ACTUAL_PROXY_CONFIG')
    path = native.STATE / ('owner_v24_dialog_' + RELEASE['install_request'] + '.json')
    raw, metadata = native.stable_read(path, 120000)
    value = document(raw)
    require(value.get('schema') == 'NOX_MODEL_REFERENCE_PROXY_INSTALL_V1'
            and value.get('request') == RELEASE['install_request']
            and value.get('source_sha') == RELEASE['install_source']
            and value.get('status') == 'APPLIED_RELOADED_USE_PENDING'
            and value.get('completed') is True and value.get('installed') is True,
            'HOLD_ACTUAL_INSTALL_RECEIPT')
    after = [x.get('after') for x in value.get('steps', []) if x.get('phase') == 'proxy_reloaded']
    require(len(after) == 1 and runtime_projection(after[0]) == RELEASE['runtime_identity'],
            'HOLD_RECEIPT_PROXY_GENERATION')
    for name, expected in RELEASE['five_postimages'].items():
        observed = value.get('files_after', {}).get(name) if name in value.get('files_after', {}) else \
                   value.get('new_artifacts', {}).get(name, {}).get('after')
        require(observed == expected, 'HOLD_INSTALL_FIVE_POSTIMAGES')
    return {'install_request': RELEASE['install_request'], 'install_source': RELEASE['install_source'],
            'private_receipt_sha256': digest(raw), 'private_receipt_bytes': len(raw),
            'proxy_generation': runtime_projection(identity), 'loaded_module_memory_identity_verified': False}


def source_readback():
    private, public = {}, {}
    for name, expected in SOURCE_PINS.items():
        raw, info = native.stable_read(native.SCRIPTS / name)
        require(digest(raw) == expected, 'HOLD_RUNTIME_SOURCE_DRIFT')
        if name in RELEASE['source_owned_identity']:
            required = RELEASE['source_owned_identity'][name]
            require(all(info[k] == required[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode', 'size')),
                    'HOLD_INSTALLED_SOURCE_INODE_DRIFT')
        if name == 'owner_model_reference_binding.py':
            required = RELEASE['five_postimages'][name]
            require((info['dev'], info['ino'], info['uid'], info['gid'], stat.S_IMODE(info['mode'])) ==
                    (required['dev'], required['ino'], 0, 0, 0o600), 'HOLD_INSTALLED_HELPER_INODE_DRIFT')
        private[name] = raw
        public[name] = {'sha256': expected, 'bytes': len(raw)}
    raw, info = native.stable_read(native.STATE / 'verified_model_reference.json', 8192)
    required = RELEASE['five_postimages']['verified_model_reference.json']
    require(digest(raw) == required['sha256'] and len(raw) == required['bytes']
            and (info['dev'], info['ino'], info['uid'], info['gid'], stat.S_IMODE(info['mode'])) ==
            (required['dev'], required['ino'], 0, 0, 0o600), 'HOLD_INSTALLED_MODEL_SNAPSHOT_DRIFT')
    public['verified_model_reference.json'] = {'sha256': digest(raw), 'bytes': len(raw)}
    return public, private


def database_binding(identity, sources):
    # Same already-reviewed auth/process reader. Only S03_DB is selected here;
    # no environment or credentials are exported or included in errors.
    node = next((n for n in ast.parse(sources['s03_memory.py']).body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'DB' for t in n.targets)), None)
    expected = ast.parse('Path(os.environ.get("S03_DB", "/root/nox/kb/knowledge.sqlite"))', mode='eval').body
    require(node is not None and ast.dump(node.value, include_attributes=False) ==
            ast.dump(expected, include_attributes=False), 'HOLD_DB_SOURCE_BINDING')
    row = identity['process']
    with (native.PROC / str(row['pid']) / 'environ').open('rb') as stream:
        raw = stream.read(262145)
    require(len(raw) <= 262144, 'HOLD_PROCESS_ENV_LIMIT')
    values = [x.split(b'=', 1)[1] for x in raw.split(b'\0') if x.startswith(b'S03_DB=')]
    require(len(values) <= 1 and (not values or values[0] == str(DB).encode()), 'HOLD_DB_RUNTIME_OVERRIDE')
    observed = native.process(row['pid'], details=False)
    require(observed is not None and observed['start_ticks'] == row['start_ticks'], 'HOLD_DB_PROCESS_DRIFT')
    info = DB.lstat()
    require(DB.resolve() == DB and stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), 'HOLD_DB_PATH')
    return {'dev': info.st_dev, 'ino': info.st_ino,
            'binding': 'PINNED_SOURCE_DEFAULT_AND_SAME_LIVE_PROXY_ENV', 'data_exported': False}


def db_identity(binding):
    info = DB.lstat()
    require(DB.resolve() == DB and stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and (info.st_dev, info.st_ino) == (binding['dev'], binding['ino']), 'HOLD_DB_FILE_REPLACED')


def own_database_snapshot(binding):
    db_identity(binding)
    with contextlib.closing(sqlite3.connect('file:' + str(DB) + '?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        dialog = db.execute('SELECT dialog_id,owner,substr(title,1,141),archived,revision,'
            'substr(created_at,1,65) FROM nox_v29_dialogs WHERE dialog_id=? AND owner=? LIMIT 2',
            (DIALOG, 'nox-single-owner')).fetchall()
        rows = db.execute('SELECT row_id,role,substr(content,1,8001),substr(ts,1,65),'
            'substr(exchange_id,1,129),length(content) FROM nox_v29_dialog_messages '
            'WHERE dialog_id=? ORDER BY row_id LIMIT 5', (DIALOG,)).fetchall()
        require(len(dialog) == 1 and dialog[0][3] == 0 and type(dialog[0][4]) is int
                and 1 <= dialog[0][4] <= 1000000 and len(dialog[0][2]) <= 140
                and len(dialog[0][5]) <= 64, 'HOLD_OWN_DIALOG_SCOPE')
        require(len(rows) in (2, 4), 'HOLD_OWN_DIALOG_ROW_COUNT')
        for row in rows:
            require(type(row[0]) is int and row[0] > 0 and row[1] in ('user', 'assistant')
                    and isinstance(row[2], str) and len(row[2]) == row[5] <= 8000
                    and len(row[2].encode()) <= 24000 and len(row[3]) <= 64
                    and re.fullmatch(r'[A-Za-z0-9_.:-]{6,128}', row[4]), 'HOLD_OWN_DIALOG_ROW_BOUNDS')
        # Return only this dialog's rows. Neither these contents nor its title
        # enter public receipts; the caller exports only hashes and row counts.
        result = {'dialog': dialog[0], 'rows': rows}
    db_identity(binding)
    return result


def verify_old_prefix(snapshot, binding):
    rows = snapshot['rows']
    require(len(rows) == 2 and [r[1] for r in rows] == ['user', 'assistant']
            and all(r[4] == OLD_EXCHANGE for r in rows), 'HOLD_PRIOR_QA_PAIR_BINDING')
    frame = native.full_turn_episode(rows[0][2], rows[1][2])
    require(frame is not None and digest(('M1|' + frame).encode()) == OLD_RECORD_SHA,
            'HOLD_PRIOR_QA_RECORD_DIGEST')
    with contextlib.closing(sqlite3.connect('file:' + str(DB) + '?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON')
        matches = db.execute('SELECT id FROM s03_items WHERE id=? AND segment=? AND provenance=? '
            'AND sha256=? AND text=? LIMIT 2', (OLD_EXCHANGE, 'M1', 'chat_turn', OLD_RECORD_SHA, frame)).fetchall()
    require(matches == [(OLD_EXCHANGE,)], 'HOLD_PRIOR_QA_S03_ROW')
    db_identity(binding)
    return {'dialog_id': DIALOG, 'messages': 2, 'exchange_id': OLD_EXCHANGE,
            'record_sha256': OLD_RECORD_SHA, 'prefix_sha256': digest(canonical(rows)),
            'history_contents_exported': False}


def verify_appended_pair(before, after, turn, binding):
    require(after['rows'][:2] == before['rows'] and len(after['rows']) == 4,
            'HOLD_PRIOR_HISTORY_CHANGED')
    old, new = before['dialog'], after['dialog']
    require(new[:4] == old[:4] and new[5] == old[5] and new[4] == old[4] + 1,
            'HOLD_DIALOG_METADATA_CHANGED')
    require(turn.exchange_id != OLD_EXCHANGE, 'HOLD_NEW_EXCHANGE_NOT_NEW')
    pair = after['rows'][2:]
    require([r[1] for r in pair] == ['user', 'assistant'] and
            [r[2] for r in pair] == [QUESTION, turn.answer] and
            all(r[4] == turn.exchange_id for r in pair) and pair[0][0] > before['rows'][-1][0],
            'HOLD_NEW_DIALOG_PAIR_CONTENT')
    frame = native.full_turn_episode(QUESTION, turn.answer)
    require(frame is not None, 'HOLD_FULL_TURN_STORAGE_BOUND')
    expected = digest(('M1|' + frame).encode())
    require(expected == turn.record_sha256, 'HOLD_STREAM_S03_DIGEST_MISMATCH')
    with contextlib.closing(sqlite3.connect('file:' + str(DB) + '?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT id FROM s03_items WHERE id=? AND segment=? AND provenance=? '
            'AND sha256=? AND text=? LIMIT 2', (turn.exchange_id, 'M1', 'chat_turn', expected, frame)).fetchall()
    require(row == [(turn.exchange_id,)], 'HOLD_NEW_S03_FRAME')
    db_identity(binding)
    return {'prior_history_preserved': True, 'prior_prefix_sha256': digest(canonical(before['rows'])),
            'prior_messages': 2, 'new_messages': 2, 'total_own_messages': 4,
            'new_exchange_id': turn.exchange_id, 'new_record_sha256': expected,
            'new_full_frame_chars': len(frame), 'segment': 'M1', 'provenance': 'chat_turn',
            'question_sha256': digest(QUESTION.encode()), 'answer_sha256': digest(turn.answer.encode()),
            'full_frame_verified': True, 'application_data_sql_writes_by_qa': 0,
            'sqlite_auxiliary_file_writes': 'POSSIBLE_WAL_SHM_CREATE_OR_UPDATE'}


def verify_history_response(value, snapshot):
    require(isinstance(value, dict) and value.get('status') == 'READY'
            and value.get('dialog_id') == DIALOG and value.get('revision') == snapshot['dialog'][4],
            'HOLD_HISTORY_RESPONSE_SCOPE')
    expected = [{'role': r[1], 'content': r[2], 'ts': r[3], 'exchange_id': r[4]} for r in snapshot['rows']]
    require(value.get('messages') == expected, 'HOLD_HTTP_SQL_HISTORY_MISMATCH')
    return {'own_messages': len(expected), 'http_sql_contents_exact': True, 'history_contents_exported': False}


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), native.NoRedirect(),
                                                 urllib.request.HTTPCookieProcessor(self.jar))
        self.counts = {'login_post': 0, 'model_post': 0, 'dialog_create_post': 0, 'get': 0}
        self.get_counts = {HISTORY_PATH: 0, MENU_PATH: 0}

    def request(self, path, data=None, timeout=20):
        if data is None:
            require(path in self.get_counts and self.get_counts[path] < (2 if path == HISTORY_PATH else 1),
                    'HOLD_GET_SCOPE_OR_REPLAY')
            self.get_counts[path] += 1
            self.counts['get'] += 1
        else:
            name = {'/chat/login': 'login_post', '/api/nox/chat': 'model_post'}.get(path)
            require(name is not None and self.counts[name] == 0, 'HOLD_POST_SCOPE_OR_REPLAY')
            self.counts[name] += 1  # Socket exceptions remain an attempted POST; never retry.
        request = urllib.request.Request(BASE + path, data=None if data is None else canonical(data),
            headers={'Content-Type': 'application/json', 'Accept':
                     'text/event-stream' if path == '/api/nox/chat' else 'application/json'})
        return self.opener.open(request, timeout=timeout)

    def raw(self, path, data=None, limit=32768):
        with self.request(path, data) as response:
            require(response.status == 200, 'HOLD_HTTP_STATUS')
            raw = response.read(limit + 1)
        require(len(raw) <= limit, 'HOLD_HTTP_BYTES')
        return raw

    def json(self, path):
        return document(self.raw(path))


class Journal:
    """Exclusive purpose reservation survives uncertain delivery and every exit."""
    def __init__(self, request, source, nonce):
        self.path = native.STATE / JOURNAL
        self.fd = None
        self.sent = False
        self.context = {'request': request, 'source_sha': source, 'nonce': nonce,
                        'install_request': RELEASE['install_request'], 'dialog_id': DIALOG}

    def __enter__(self):
        try:
            os.mkdir(self.path, 0o700)
        except FileExistsError:
            raise Hold('HOLD_QA_ALREADY_RESERVED_NO_RETRY') from None
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.identity = os.fstat(self.fd)
        try:
            self.check()
            self.write('reservation.json', self.context | {'automatic_retry_allowed': False})
            parent = os.open(native.STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(parent)
            finally: os.close(parent)
            return self
        except BaseException:
            os.close(self.fd); self.fd = None
            raise

    def check(self):
        require(self.fd is not None, 'HOLD_QA_JOURNAL_CLOSED')
        a, b = os.fstat(self.fd), self.path.lstat()
        require(stat.S_ISDIR(a.st_mode) and a.st_uid == os.geteuid() and stat.S_IMODE(a.st_mode) == 0o700
                and (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino) ==
                    (self.identity.st_dev, self.identity.st_ino), 'HOLD_QA_JOURNAL_IDENTITY')

    def write(self, name, value):
        require(name in ('reservation.json', 'model_post_intent.json', 'outcome.json',
                         'counter_before.json', 'counter_after.json'), 'HOLD_QA_JOURNAL_NAME')
        self.check()
        raw = canonical(value)
        require(len(raw) <= MAX_RECEIPT, 'HOLD_QA_JOURNAL_BYTES')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            position = 0
            while position < len(raw):
                n = os.write(fd, raw[position:])
                require(n > 0, 'HOLD_QA_JOURNAL_SHORT_WRITE'); position += n
            os.fsync(fd)
            expected = os.fstat(fd)
        finally:
            os.close(fd)
        self.check()
        verify = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            actual = os.fstat(verify)
            observed = os.read(verify, MAX_RECEIPT + 1)
            current = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            require(observed == raw and stat.S_ISREG(actual.st_mode) and stat.S_IMODE(actual.st_mode) == 0o600
                    and actual.st_uid == os.geteuid() and actual.st_nlink == 1
                    and (expected.st_dev, expected.st_ino) == (actual.st_dev, actual.st_ino) ==
                        (current.st_dev, current.st_ino), 'HOLD_QA_JOURNAL_READBACK')
        finally:
            os.close(verify)
        os.fsync(self.fd)

    def send(self, client):
        require(not self.sent, 'HOLD_QA_POST_REPLAY')
        value = body(self.context['nonce'])
        self.write('model_post_intent.json', self.context | {
            'body_sha256': digest(canonical(value)), 'question_sha256': digest(QUESTION.encode()),
            'client_history_messages': 0, 'server_prior_messages': 2, 'create_posts': 0,
            'max_tokens': 256, 'single_send_attempt': True, 'uncertain_result_never_retried': True})
        self.check()
        self.sent = True
        return client.request('/api/nox/chat', value)

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd); self.fd = None


class ZeroSendContinuation(Journal):
    """One fixed child of one proven-unsent purpose; old records stay intact."""
    def __init__(self, request, source):
        super().__init__(request, source, '0' * 32)
        self.prior_path, self.path = self.path, self.path / CONTINUATION
        self.chain = []
        self.prior_fd = None
        self.prior_identity = None
        self.original_files = {}
        self.child_created = False

    @staticmethod
    def directory_identity(info):
        return tuple(getattr(info, name) for name in
                     ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode'))

    @staticmethod
    def file_identity(info):
        return tuple(getattr(info, name) for name in ('st_dev', 'st_ino', 'st_uid',
            'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))

    def open_prior(self):
        require(self.prior_fd is None and not self.chain, 'HOLD_CONTINUATION_OPEN_REENTRY')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        root_fd = os.open('/', flags)
        self.chain.append((None, None, root_fd, self.directory_identity(os.fstat(root_fd))))
        parent = root_fd
        try:
            for part in native.STATE.parts[1:]:
                require(part not in ('', '.', '..'), 'HOLD_CONTINUATION_PARENT_PATH')
                child = os.open(part, flags, dir_fd=parent)
                self.chain.append((parent, part, child, self.directory_identity(os.fstat(child))))
                parent = child
            self.prior_fd = os.open(JOURNAL, flags, dir_fd=parent)
            self.prior_identity = self.directory_identity(os.fstat(self.prior_fd))
            self.check_prior()
        except BaseException:
            self.close_prior()
            raise

    def read_prior(self, name, maximum):
        require(name in ('reservation.json', 'outcome.json'), 'HOLD_CONTINUATION_PRIOR_PATH')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=self.prior_fd)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                    and before.st_gid == os.getegid() and stat.S_IMODE(before.st_mode) == 0o600
                    and before.st_nlink == 1 and 0 < before.st_size <= maximum,
                    'HOLD_CONTINUATION_PRIOR_FILE_TYPE')
            raw = os.pread(fd, maximum + 1, 0)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=self.prior_fd, follow_symlinks=False)
            identity = self.file_identity(before)
            require(len(raw) == before.st_size and identity == self.file_identity(after)
                    == self.file_identity(named), 'HOLD_CONTINUATION_PRIOR_FILE_DRIFT')
            previous = self.original_files.get(name)
            require(previous is None or previous == (identity, raw),
                    'HOLD_CONTINUATION_PRIOR_FILE_REPLACED')
            self.original_files[name] = (identity, raw)
            return document(raw)
        finally:
            os.close(fd)

    def check_prior(self):
        require(self.prior_fd is not None and self.chain, 'HOLD_CONTINUATION_PRIOR_CLOSED')
        for parent, name, fd, expected in self.chain:
            require(self.directory_identity(os.fstat(fd)) == expected,
                    'HOLD_CONTINUATION_PARENT_IDENTITY')
            if parent is not None:
                require(self.directory_identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                        == expected, 'HOLD_CONTINUATION_PARENT_REPLACED')
        info = os.fstat(self.prior_fd)
        require(self.directory_identity(info) == self.prior_identity ==
                self.directory_identity(os.stat(JOURNAL, dir_fd=self.chain[-1][2], follow_symlinks=False))
                and stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_uid == os.geteuid() and info.st_gid == os.getegid(),
                'HOLD_CONTINUATION_PRIOR_DIRECTORY')
        names = set()
        with os.scandir(self.prior_fd) as entries:
            for entry in entries:
                names.add(entry.name)
                require(len(names) <= 3, 'HOLD_CONTINUATION_PRIOR_SCOPE')
        require('model_post_intent.json' not in names, 'HOLD_CONTINUATION_PRIOR_SEND_INTENT')
        if not self.child_created and CONTINUATION in names:
            raise Hold('HOLD_CONTINUATION_ALREADY_RESERVED_NO_RETRY')
        expected = {'reservation.json', 'outcome.json'} | ({CONTINUATION} if self.child_created else set())
        require(names == expected, 'HOLD_CONTINUATION_PRIOR_SCOPE')
        outcome = self.read_prior('outcome.json', MAX_RECEIPT)
        raw = self.original_files['outcome.json'][1]
        require(len(raw) == PRIOR_OUTCOME_BYTES and digest(raw) == PRIOR_OUTCOME_SHA,
                'HOLD_CONTINUATION_PRIOR_OUTCOME_PIN')
        require(outcome.get('request') == PRIOR_REQUEST and outcome.get('source_sha') == PRIOR_SOURCE
                and outcome.get('status') == 'HOLD_OWNER_PRIORITY_BUSY_OR_STALE'
                and outcome.get('unknown_delivery_possible') is False
                and outcome.get('used') is False and outcome.get('completed') is False
                and type(outcome.get('owner_chat_posts')) is int and outcome['owner_chat_posts'] == 0
                and type(outcome.get('model_posts')) is int and outcome['model_posts'] == 0
                and outcome.get('http_counts') == {
                    'dialog_create_post': 0, 'get': 2, 'login_post': 1, 'model_post': 0},
                'HOLD_CONTINUATION_PRIOR_NOT_PROVEN_UNSENT')
        reservation = self.read_prior('reservation.json', 4096)
        require(type(reservation) is dict and set(reservation) == {'request', 'source_sha', 'nonce',
                'install_request', 'dialog_id', 'automatic_retry_allowed'}
                and reservation['request'] == PRIOR_REQUEST and reservation['source_sha'] == PRIOR_SOURCE
                and reservation['install_request'] == RELEASE['install_request']
                and reservation['dialog_id'] == DIALOG and reservation['automatic_retry_allowed'] is False
                and type(reservation['nonce']) is str
                and re.fullmatch('[a-f0-9]{32}', reservation['nonce']),
                'HOLD_CONTINUATION_PRIOR_RESERVATION')
        self.context['nonce'] = reservation['nonce']
        self.context.update(prior_request=PRIOR_REQUEST, prior_source_sha=PRIOR_SOURCE,
                            prior_outcome_sha256=PRIOR_OUTCOME_SHA)

    def preflight(self):
        self.open_prior()
        return {'prior_request': PRIOR_REQUEST, 'prior_source_sha': PRIOR_SOURCE,
                'prior_outcome_sha256': PRIOR_OUTCOME_SHA, 'prior_outcome_bytes': PRIOR_OUTCOME_BYTES,
                'prior_owner_chat_posts': 0, 'prior_unknown_delivery_possible': False,
                'prior_root_send_intent_absent': True, 'continuation_slots': 1,
                'old_journal_preserved': True, 'automatic_retry_allowed': False}

    def __enter__(self):
        self.check_prior()
        try:
            os.mkdir(CONTINUATION, 0o700, dir_fd=self.prior_fd)
        except FileExistsError:
            raise Hold('HOLD_CONTINUATION_ALREADY_RESERVED_NO_RETRY') from None
        self.child_created = True  # An ambiguous later failure never removes this reservation.
        try:
            os.fsync(self.prior_fd)
            self.fd = os.open(CONTINUATION, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=self.prior_fd)
            self.identity = os.fstat(self.fd)
            self.check()
            self.write('reservation.json', self.context | {'automatic_retry_allowed': False,
                       'known_zero_send_continuation': True, 'max_owner_chat_posts_across_attempts': 1})
            os.fsync(self.prior_fd)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def check(self):
        self.check_prior()
        super().check()

    def close_prior(self):
        if self.prior_fd is not None:
            os.close(self.prior_fd); self.prior_fd = None
        for _, _, fd, _ in reversed(self.chain):
            os.close(fd)
        self.chain = []

    def __exit__(self, *args):
        try:
            super().__exit__(*args)
        finally:
            self.close_prior()


def counter_snapshot():
    """Return private exact bytes and a safe projection, never an admission."""
    raw, info = native.stable_read(COUNTER, MAX_COUNTER_BYTES)
    value = document(raw)
    require(type(value) is dict and type(value.get('inflight')) is int
            and 0 <= value['inflight'] <= 100000, 'HOLD_LEGACY_COUNTER_SCHEMA')
    # The legacy writer preserves unknown old keys. They are not interpreted,
    # used as a gate, or exported. Full bytes go only to owned private evidence.
    timestamps = {}
    for name in ('last_ts', 'last_start', 'last_end'):
        if name in value:
            require(type(value[name]) in (int, float) and 0 <= value[name] < 100000000000,
                    'HOLD_COUNTER_TIMESTAMP_SCHEMA')
            timestamps[name] = value[name]
    require(raw.decode('utf-8').encode('utf-8') == raw, 'HOLD_COUNTER_UTF8')
    return raw, {'path': str(COUNTER),
        'sha256': digest(raw), 'bytes': len(raw), 'inflight': value['inflight'],
        **timestamps, 'extra_key_count': len(set(value) - {'inflight', 'last_ts', 'last_start', 'last_end'}),
        'metadata': info, 'counter_writes': 0, 'expected_value_assigned': False,
        'raw_contents_exported': False,
        'writer_key_present': 'writer' in value, 'activity_schema_key_present': 'activity_schema' in value,
        'historical_requests_resolved': False,
        'snapshot_is_atomic_owner_admission': False}


def write_counter_evidence(journal, name, raw, projection):
    require(name in ('counter_before.json', 'counter_after.json')
            and digest(raw) == projection['sha256'] and len(raw) == projection['bytes']
            <= MAX_COUNTER_BYTES, 'HOLD_COUNTER_EVIDENCE_SCOPE')
    value = {'schema': 'NOX_PRIVATE_COUNTER_EVIDENCE_V1', **journal.context,
        'counter_path': str(COUNTER), 'raw_utf8': raw.decode('utf-8'),
        'counter_sha256': projection['sha256'], 'counter_bytes': projection['bytes'],
        'counter_metadata': projection['metadata'], 'raw_contents_exported': False}
    journal.write(name, value)  # Existing 0600 no-clobber, fsync, exact readback.
    written, info = native.stable_read(journal.path / name, MAX_RECEIPT)
    require(written == canonical(value) and stat.S_IMODE(info['mode']) == 0o600,
            'HOLD_PRIVATE_COUNTER_READBACK')
    journal.check()
    return {'path': str(journal.path / name), 'sha256': digest(written), 'bytes': len(written),
            'metadata': info, 'counter_sha256': projection['sha256'],
            'counter_bytes': projection['bytes'], 'readback_exact': True,
            'raw_contents_exported': False, 'counter_file_writes': 0}


def safe_priority_diagnostic():
    """Later bounded observation; never infer the cause of the earlier HOLD."""
    result = {'failure_subcause': 'UNKNOWN', 'later_observation_only': True, 'files': {}}
    for name in ('CHAT_ACTIVE', 'MODE', 'status.json'):
        try:
            raw, info = native.stable_read(native.STATE / 'priority' / name,
                                          32768 if name == 'status.json' else 64)
            row = {'age_seconds': round(time.time() - info['mtime_ns'] / 1e9, 3), 'bytes': len(raw)}
            if name == 'status.json':
                value = document(raw)
                require(type(value) is dict, 'HOLD_PRIORITY_DIAGNOSTIC_SCHEMA')
                row['mode'] = value.get('mode') if value.get('mode') in ('ACTIVE', 'IDLE') else 'UNRECOGNIZED'
                row['train_pause'] = value.get('train_pause') if type(value.get('train_pause')) is bool else None
            else:
                allowed = (b'0', b'1') if name == 'CHAT_ACTIVE' else (b'ACTIVE', b'IDLE')
                row['value'] = raw.strip().decode() if raw.strip() in allowed else 'UNRECOGNIZED'
            result['files'][name] = row
        except Exception as error:
            result['files'][name] = {'state': status_code(error)}
    return result


@contextlib.contextmanager
def deadline():
    require(threading.current_thread() is threading.main_thread()
            and signal.getitimer(signal.ITIMER_REAL) == (0., 0.), 'HOLD_DEADLINE_CONTEXT')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise Hold('HOLD_QA_WALL_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, MAX_WALL)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def status_code(error):
    return str(error) if isinstance(error, Hold) and re.fullmatch('HOLD_[A-Z0-9_]+', str(error)) else \
        'HOLD_' + type(error).__name__.upper()


def run():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(os.geteuid() == 0 and re.fullmatch('[0-9]{1,24}', request)
            and re.fullmatch('[a-f0-9]{40}', source), 'HOLD_OWNER_CONTEXT')
    report = {'schema': 'NOX_MODEL_REFERENCE_CHANGED_PATH_QA_V1', 'request': request, 'source_sha': source,
        'status': 'HOLD_NOT_STARTED', 'completed': False, 'used': False, 'accepted': False,
        'unknown_delivery_possible': False,
        'semantic_acceptance': 'PENDING_HUMAN_REVIEW', 'model_reloads': 0, 'service_mutations': 0,
        'counter_resets': 0, 'dialog_create_posts': 0, 'external_http': 0, 'automatic_retry_allowed': False,
        'history_contents_exported': False, 'exact_model_input_tokens': None,
        'owner_chat_posts': 0, 'backend_model_http_posts': 'NOT_DIRECTLY_OBSERVED',
        'http_count_scope': 'OWNER_UI_CLIENT_ONLY; SLOT_GETS_ARE_SEPARATE_OWNER_IDLE_OBSERVATIONS',
        'atomic_owner_admission_lease': False,
        'scope': 'ONE_KNOWN_ZERO_SEND_CONTINUATION_EXISTING_OWN_QA_DIALOG',
        'known_prior_http_counts': {'login_post': 1, 'get': 2, 'model_post': 0, 'dialog_create_post': 0},
        'owner_chat_posts_across_known_attempts': 0}
    client = Client()
    journal = None
    waiter = None
    try:
        with deadline(), native.maintenance_lease() as lock:
            require(lock == {'dev': 36, 'ino': 59886214}, 'HOLD_MAINTENANCE_LOCK_PIN')
            for path in (native.ROOT.parent, native.ROOT, native.SCRIPTS, native.STATE):
                native.checked_directory(path)
            native.global_stop_guard()
            journal = ZeroSendContinuation(request, source)
            # Read and pin the real existing outcome before any new HTTP or
            # continuation ownership write. A copied report alone is no grant.
            report['zero_send_continuation'] = journal.preflight()
            report['source_readback'], sources = source_readback()
            identity = native.service_identity()
            report['installed_release'] = installed_release(identity)
            binding = database_binding(identity, sources)
            report['database_binding'] = binding
            before = own_database_snapshot(binding)
            report['prior_history'] = verify_old_prefix(before, binding)
            require(report['prior_history']['prefix_sha256'] == PRIOR_PREFIX_SHA,
                    'HOLD_CONTINUATION_PRIOR_HISTORY_CHANGED')
            report['owner_admission'] = native.owner_idle()
            baseline_counter, report['counter_before_login'] = counter_snapshot()
            with journal:
                try:
                    report['idle_wait'] = {}
                    waiter = LoginIdleWait(native, document, counter_snapshot, baseline_counter,
                                           identity, lock, report['idle_wait'])
                    waiter.capture()
                    report['phase'] = 'OFFICIAL_LOGIN'
                    credential_path = native.resolve_password_path(sources['chat_proxy.py'].decode(),
                        common_source=sources['common.py'].decode())
                    credential, info = native.stable_read(credential_path, 4096)
                    require(not info['mode'] & 0o077 and 6 <= len(credential.strip()) <= 4096,
                            'HOLD_CREDENTIAL_SCOPE')
                    try:
                        client.raw('/chat/login', {'password': credential.decode().strip()})
                    finally:
                        credential = None
                    require(any(True for _ in client.jar), 'HOLD_LOGIN_SESSION')
                    report['history_http_before'] = verify_history_response(client.json(HISTORY_PATH), before)
                    menu = client.raw(MENU_PATH, limit=44000)
                    require(len(menu) == 43021 and digest(menu) == MENU_SHA, 'HOLD_SERVED_MENU_POSTIMAGE')
                    report['menu'] = {'path': MENU_PATH, 'sha256': MENU_SHA, 'bytes': len(menu),
                                      'authenticated_served_postimage': True, 'visual_click_test': False}
                    # Reuse the accepted single-login wait. Its polls observe only;
                    # they never clear flags or retry authentication/model delivery.
                    def final_fence():
                        journal.check()
                        source_readback()
                        native.require_same_service(identity)
                        installed_release(identity)
                        arbiter_raw, arbiter_info = evidence_read(native.SCRIPTS / 'nox_priority_arbiter.py', 32768)
                        require(digest(arbiter_raw) == ARBITER_SHA
                                and arbiter_info == report['idle_wait']['arbiter_source'],
                                'HOLD_ARBITER_SOURCE_DRIFT_AFTER_WAIT')
                        require(own_database_snapshot(binding) == before, 'HOLD_OWN_HISTORY_CHANGED_BEFORE_SEND')
                    report['owner_admission_after_wait'] = waiter.wait()
                    final_fence()
                    before_counter, report['counter_before_send'] = counter_snapshot()
                    require(before_counter == baseline_counter, 'HOLD_COUNTER_CHANGED_BEFORE_SEND')
                    report['counter_before_send']['private_evidence'] = write_counter_evidence(
                        journal, 'counter_before.json', before_counter, report['counter_before_send'])
                    report['owner_admission_before_send'] = waiter.final_check()
                    report['phase'] = 'ONE_CHANGED_PATH_QUESTION'
                    started = time.monotonic()
                    with journal.send(client) as response:
                        require(response.status == 200 and 'text/event-stream' in
                                response.headers.get('Content-Type', ''), 'HOLD_CHAT_RESPONSE_TYPE')
                        turn = read_v24(response, DIALOG, started=started)
                    report['used'] = True
                    report['stream'] = turn.safe_receipt()
                    after = own_database_snapshot(binding)
                    report['history_and_s03'] = verify_appended_pair(before, after, turn, binding)
                    report['history_http_after'] = verify_history_response(client.json(HISTORY_PATH), after)
                    native.require_same_service(identity)
                    source_readback()
                    after_counter, report['counter_after_persistence'] = counter_snapshot()
                    report['counter_after_persistence']['private_evidence'] = write_counter_evidence(
                        journal, 'counter_after.json', after_counter, report['counter_after_persistence'])
                    report['counter_observation'] = {
                        'stage_before': 'AFTER_LOGIN_IDLE_AND_FINAL_SOURCE_HISTORY_FENCE_BEFORE_DURABLE_INTENT',
                        'stage_after': 'NORMAL_EOF_FULL_M1_AND_HTTP_SQL_HISTORY_VERIFIED',
                        'same_numeric_inflight': report['counter_before_send']['inflight'] ==
                            report['counter_after_persistence']['inflight'],
                        'numeric_delta': report['counter_after_persistence']['inflight'] -
                            report['counter_before_send']['inflight'],
                        'during_request_counter_observed': False, 'historical_requests_resolved': False,
                        'expected_value_assigned': False, 'counter_writes': 0}
                    answer_bytes = turn.answer.encode()
                    require(len(answer_bytes) <= 4096, 'HOLD_OWN_ANSWER_BYTES')
                    report['own_synthetic_answer'] = {'text': turn.answer, 'sha256': digest(answer_bytes),
                        'bytes': len(answer_bytes), 'prior_history_included': False,
                        'full_observed_basename_present': MODEL_REFERENCE in turn.answer,
                        'model_alias_present': 'deepseek-v41-flash-iq2xxs' in turn.answer.lower(),
                        'obsolete_status_name_present': 'nox-s1-l05' in turn.answer.lower()}
                    report.update(status='TRANSPORT_AND_PERSISTENCE_COMPLETE_SEMANTIC_REVIEW_PENDING',
                        completed=True, phase='COMPLETED', system_prefix_bound_path_completion_inferred=True,
                        system_prefix_exact_bytes=None, narrow_identity_path_evidence='PINNED_SOURCE_AND_FRESH_RELOADED_PROXY',
                        actual_model_input_trace_observed=False,
                        loaded_module_memory_identity_verified=False)
                except BaseException as error:
                    if isinstance(error, Hold) and ('PRIORITY' in str(error) or 'IDLE' in str(error)):
                        report['priority_diagnostic_after_hold'] = safe_priority_diagnostic()
                    report.update(status=status_code(error), completed=False, phase='HOLD',
                        unknown_delivery_possible=client.counts['model_post'] > 0)
                finally:
                    report['http_counts'] = dict(client.counts)
                    report['model_posts'] = client.counts['model_post']
                    report['owner_chat_posts'] = client.counts['model_post']
                    report['owner_chat_posts_across_known_attempts'] = client.counts['model_post']
                    report['private_receipt_path'] = str(journal.path / 'outcome.json')
                    journal.write('outcome.json', report)
    except BaseException as error:
        report.update(status=status_code(error), completed=False, phase='HOLD',
            http_counts=dict(client.counts), model_posts=client.counts['model_post'],
            owner_chat_posts=client.counts['model_post'],
            owner_chat_posts_across_known_attempts=client.counts['model_post'],
            unknown_delivery_possible=client.counts['model_post'] > 0)
    finally:
        if waiter is not None:
            waiter.close()
        if journal is not None:
            journal.close_prior()
    return report


def entry():
    try:
        report = run()
    except BaseException as error:
        report = {'schema': 'NOX_MODEL_REFERENCE_CHANGED_PATH_QA_V1', 'status': status_code(error),
                  'completed': False, 'accepted': False, 'automatic_retry_allowed': False}
    output = canonical({'kind': 'model_reference_changed_path_qa', 'data': report})
    if len(output) > MAX_RECEIPT:
        output = canonical({'kind': 'model_reference_changed_path_qa', 'data': {
            'status': 'HOLD_QA_PUBLIC_BOUND', 'completed': False, 'automatic_retry_allowed': False}})
        report['completed'] = False
    print('NOX_MAINT_REPAIR=' + output.decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(report.get('completed') is True).lower(), flush=True)
    return 0 if report.get('completed') is True else 2


if __name__ == '__main__':
    raise SystemExit(entry())
