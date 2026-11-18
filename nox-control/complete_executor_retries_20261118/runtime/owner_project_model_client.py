#!/usr/bin/env python3
"""One bounded background client to the existing loopback NOX model.

Prompt size is checked through that server's actual template and tokenizer.
The model slot is separate from the three OS worker slots. No new model is
loaded; no endpoint, command, credential or environment comes from model text.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import threading
import time
import urllib.error
import urllib.request

from owner_project_planner import PlannerHold, canonical, require, sha

BASE_URL = 'http://127.0.0.1:8098'
MODEL_LOCK = Path('/root/nox/state/dispatcher/project_model_slot.lock')
MAX_REPLY = 256 * 1024
MODEL_TURN_SECONDS = 360
MODEL_WAIT_SECONDS = 2 * MODEL_TURN_SECONDS + 30
MODEL_POLL_SECONDS = .25
TURN_PAGE_BYTES = 4096
TURN_SCHEMA = 'NOX_PROJECT_MODEL_TURNS_V1'
# POSIX byte locks are process scoped. Serialize metadata operations and fd
# closes within a process; flock remains the exclusive inference lock.
_TURN_LOCAL_LOCK = threading.RLock()


def process_identity(pid):
    try:
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
        if fields[0] in ('Z', 'X', 'x'):
            return None
        return {'pid': pid, 'start_ticks': int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PlannerHold('HOLD_PROJECT_MODEL_REDIRECT')


def request_json(path, payload=None, timeout=15):
    require(path in ('/props', '/slots', '/v1/models', '/apply-template',
                     '/tokenize', '/v1/chat/completions'), 'MODEL_ENDPOINT')
    data = canonical(payload) if payload is not None else None
    request = urllib.request.Request(BASE_URL + path, data=data,
        method='POST' if data is not None else 'GET',
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),
                NoRedirect()).open(request, timeout=timeout) as response:
            require(response.status == 200, 'MODEL_HTTP_STATUS')
            raw = response.read(MAX_REPLY + 1)
    except (OSError, ValueError) as exc:
        raise PlannerHold('HOLD_PROJECT_MODEL_HTTP_UNAVAILABLE') from exc
    require(len(raw) <= MAX_REPLY, 'MODEL_RESPONSE_BOUND')
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise PlannerHold('HOLD_PROJECT_MODEL_RESPONSE_JSON') from exc


def compact(messages):
    """Reduce only model context; never change the actual source snapshot."""
    if len(messages) > 4:
        del messages[2:4]
        return True
    intro = json.loads(messages[1]['content'])
    sources = intro.get('initial_source_files') or {}
    if sources:
        sources.pop(max(sources, key=lambda key: len(sources[key])))
        intro['initial_source_files'] = sources
        messages[1]['content'] = json.dumps(intro, ensure_ascii=False)
        return True
    if len(messages) >= 4 and messages[-1]['content'].startswith('Observed tool result (data):\n'):
        prefix = 'Observed tool result (data):\n'
        result = json.loads(messages[-1]['content'][len(prefix):])
        if isinstance(result.get('content'), str) and len(result['content']) > 1200:
            lines = result['content'].splitlines(keepends=True)
            if len(lines) > 1:
                result['content'] = ''.join(lines[:max(1, len(lines) // 2)])
                result['context_excerpt_truncated'] = True
                result['next_line'] = result.get('start_line', 1) + max(1, len(lines) // 2)
                messages[-1]['content'] = prefix + json.dumps(result, ensure_ascii=False)
                return True
        if isinstance(result.get('output'), str) and len(result['output']) > 1800:
            result['output'] = result['output'][-1800:]
            result['output_excerpt_truncated'] = True
            messages[-1]['content'] = prefix + json.dumps(result, ensure_ascii=False)
            return True
        if isinstance(result.get('matches'), list) and len(result['matches']) > 6:
            result['matches'] = result['matches'][:len(result['matches']) // 2]
            result['matches_excerpt_truncated'] = True
            messages[-1]['content'] = prefix + json.dumps(result, ensure_ascii=False)
            return True
    if len(messages) >= 4 and len(messages[-2]['content']) > 1000:
        value = messages[-2]['content']
        try:
            kind = json.loads(value).get('action')
        except (ValueError, TypeError, AttributeError):
            kind = 'prior_action'
        messages[-2]['content'] = json.dumps({'action': kind,
            'context_summary_only': True, 'previous_response_sha256': sha(value.encode())})
        return True
    return False


class LocalModelClient:
    def __init__(self, *, expected_model_id, stop_check, heartbeat=lambda: None,
                 http=request_json, lock_path=MODEL_LOCK, max_tokens=900):
        require(isinstance(expected_model_id, str) and 1 <= len(expected_model_id) <= 500,
                'MODEL_ID_PIN')
        require(callable(stop_check) and callable(heartbeat) and callable(http),
                'MODEL_CALLBACKS')
        require(type(max_tokens) is int and 128 <= max_tokens <= 1200, 'MODEL_TOKEN_BUDGET')
        self.model_id, self.stop_check, self.heartbeat = expected_model_id, stop_check, heartbeat
        self.http, self.lock_path, self.max_tokens = http, Path(lock_path), max_tokens

    def _alive(self):
        require(self.stop_check() is False, 'OWNER_STOP_OR_CLAIM_LOST')
        self.heartbeat()

    def _lock_current(self, fd):
        info = os.fstat(fd)
        named = self.lock_path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_nlink == 1
                and stat.S_ISREG(named.st_mode)
                and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino),
                'MODEL_LOCK_OWNER_OR_IDENTITY')

    def _turns(self, fd, change, deadline, *, check_alive=True):
        """Update at most three ephemeral turn tickets in the existing lock.

        The byte lock protects only this short metadata operation and is
        independent of flock on Linux. Dead/reused PIDs and expired tickets
        cannot reserve the next turn. The native task queue remains untouched.
        """
        with _TURN_LOCAL_LOCK:
            while True:
                if check_alive:
                    self._alive()
                self._lock_current(fd)
                require(time.monotonic() < deadline, 'MODEL_SLOT_METADATA_BUSY')
                try:
                    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0)
                    break
                except BlockingIOError:
                    time.sleep(MODEL_POLL_SECONDS)
            try:
                self._lock_current(fd)
                raw = os.pread(fd, TURN_PAGE_BYTES + 1, 0)
                require(len(raw) in (0, TURN_PAGE_BYTES), 'MODEL_TURN_STATE_BOUND')
                if raw:
                    try:
                        state = json.loads(raw)
                    except ValueError as exc:
                        raise PlannerHold('HOLD_PROJECT_PLANNER_MODEL_TURN_STATE_JSON') from exc
                    require(isinstance(state, dict) and set(state) == {'schema', 'waiters'}
                            and state['schema'] == TURN_SCHEMA
                            and canonical(state) == raw.rstrip(b' '), 'MODEL_TURN_STATE_SCHEMA')
                    rows = state['waiters']
                else:
                    rows = []
                require(isinstance(rows, list) and len(rows) <= 3, 'MODEL_TURN_STATE_SIZE')
                for row in rows:
                    require(isinstance(row, dict)
                            and set(row) == {'pid', 'start_ticks', 'token', 'expires'}
                            and type(row['pid']) is int and row['pid'] > 0
                            and type(row['start_ticks']) is int and row['start_ticks'] > 0
                            and isinstance(row['token'], str) and len(row['token']) == 32
                            and all(c in '0123456789abcdef' for c in row['token'])
                            and type(row['expires']) in (int, float)
                            and math.isfinite(row['expires']), 'MODEL_TURN_TICKET')
                require(len({row['token'] for row in rows}) == len(rows), 'MODEL_TURN_DUPLICATE')
                now = time.monotonic()
                rows = [row for row in rows if row['expires'] > now
                        and process_identity(row['pid']) == {
                            'pid': row['pid'], 'start_ticks': row['start_ticks']}]
                result = change(rows)
                data = canonical({'schema': TURN_SCHEMA, 'waiters': rows})
                require(len(rows) <= 3 and len(data) <= TURN_PAGE_BYTES, 'MODEL_TURN_STATE_SIZE')
                page = data.ljust(TURN_PAGE_BYTES, b' ')
                if page != raw:
                    # A fixed-size single write avoids a trailing-old-bytes
                    # window if a worker exits between write and truncate.
                    require(os.pwrite(fd, page, 0) == len(page), 'MODEL_TURN_STATE_WRITE')
                return result
            finally:
                fcntl.lockf(fd, fcntl.LOCK_UN, 1, 0)

    def _release_slot(self, fd, token):
        try:
            self._turns(fd, lambda rows: rows.__setitem__(slice(None),
                [row for row in rows if row['token'] != token]),
                time.monotonic() + 2, check_alive=False)
        finally:
            with _TURN_LOCAL_LOCK:
                os.close(fd)

    def _slot_lock(self):
        path = self.lock_path
        require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)),
                'MODEL_LOCK_PATH')
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        token = os.urandom(16).hex()
        deadline = time.monotonic() + MODEL_WAIT_SECONDS
        try:
            identity = process_identity(os.getpid())
            require(identity is not None, 'MODEL_WORKER_IDENTITY')
            def register(rows):
                require(len(rows) < 3, 'MODEL_WAITER_LIMIT')
                rows.append({**identity, 'token': token, 'expires': deadline})
            self._turns(fd, register, deadline)

            def acquire(rows):
                require(any(row['token'] == token for row in rows), 'MODEL_TURN_TICKET_LOST')
                if rows[0]['token'] != token:
                    return None
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return None
                held_until = time.monotonic() + MODEL_TURN_SECONDS
                rows[0]['expires'] = held_until
                return held_until

            while True:
                require(process_identity(os.getpid()) == identity, 'MODEL_WORKER_IDENTITY')
                require(time.monotonic() < deadline, 'MODEL_SLOT_BUSY')
                held_until = self._turns(fd, acquire, deadline)
                if held_until is not None:
                    self._alive()
                    return fd, token, held_until
                time.sleep(MODEL_POLL_SECONDS)
        except BaseException:
            try:
                self._release_slot(fd, token)
            except (OSError, ValueError, PlannerHold):
                pass
            raise

    def __call__(self, messages):
        self._alive()
        waiting_started = time.monotonic()
        fd, token, turn_deadline = self._slot_lock()
        waited_ms = round((time.monotonic() - waiting_started) * 1000)
        try:
            def http(path, payload=None, timeout=15):
                self._alive()
                remaining = turn_deadline - time.monotonic()
                require(remaining > 0, 'MODEL_TURN_TIMEOUT')
                result = self.http(path, payload, timeout=min(timeout, remaining))
                self._alive()
                require(time.monotonic() < turn_deadline, 'MODEL_TURN_TIMEOUT')
                return result

            models = http('/v1/models')
            require(isinstance(models, dict) and isinstance(models.get('data'), list)
                    and any(isinstance(x, dict) and x.get('id') == self.model_id
                            for x in models['data']), 'MODEL_ID_CHANGED')
            props = http('/props')
            settings = props.get('default_generation_settings') if isinstance(props, dict) else None
            context = settings.get('n_ctx') if isinstance(settings, dict) else None
            require(type(context) is int and context >= 2048, 'MODEL_CONTEXT_UNKNOWN')
            slot_deadline = time.monotonic() + 120
            while True:
                self._alive()
                slots = http('/slots')
                require(isinstance(slots, list) and len(slots) >= 2, 'MODEL_SLOT_SCHEMA')
                if any(isinstance(s, dict) and s.get('is_processing') is False for s in slots):
                    break
                require(time.monotonic() < slot_deadline, 'MODEL_NO_AVAILABLE_SLOT')
                time.sleep(.5)
            current = copy.deepcopy(messages)
            for _ in range(24):
                self._alive()
                rendered = http('/apply-template', {'messages': current})
                require(isinstance(rendered, dict) and isinstance(rendered.get('prompt'), str),
                        'MODEL_TEMPLATE_SCHEMA')
                tokenized = http('/tokenize', {'content': rendered['prompt'],
                    'add_special': False, 'parse_special': True, 'with_pieces': False})
                tokens = tokenized.get('tokens') if isinstance(tokenized, dict) else None
                require(isinstance(tokens, list) and all(type(x) is int for x in tokens),
                        'MODEL_TOKENIZER_SCHEMA')
                input_tokens = len(tokens)
                if input_tokens + self.max_tokens + 128 <= context:
                    break
                require(compact(current), 'MODEL_CONTEXT_TOO_LARGE')
            else:
                raise PlannerHold('HOLD_PROJECT_MODEL_CONTEXT_COMPACTION_BUDGET')
            self._alive()
            payload = {'model': self.model_id, 'messages': current, 'stream': False,
                       'temperature': .1, 'max_tokens': self.max_tokens,
                       'response_format': {'type': 'json_object'}}
            template = props.get('chat_template') if isinstance(props, dict) else None
            if isinstance(template, str) and 'enable_thinking' in template:
                payload['chat_template_kwargs'] = {'enable_thinking': False}
            started = time.monotonic()
            response = http('/v1/chat/completions', payload, timeout=180)
            self._alive()
            try:
                choice = response['choices'][0]
                reply = choice['message']['content']
                finish = choice.get('finish_reason')
            except (KeyError, IndexError, TypeError) as exc:
                raise PlannerHold('HOLD_PROJECT_MODEL_COMPLETION_SCHEMA') from exc
            require(isinstance(reply, str) and reply.strip() and finish not in ('length', 'content_filter'),
                    'MODEL_INCOMPLETE_RESPONSE')
            usage = response.get('usage') if isinstance(response.get('usage'), dict) else {}
            return {'content': reply, 'metadata': {
                'endpoint': BASE_URL + '/v1/chat/completions', 'model_id': self.model_id,
                'input_tokens_measured': input_tokens, 'n_ctx': context,
                'max_output_tokens': self.max_tokens, 'finish_reason': finish,
                'measured_prompt_size': input_tokens,
                'completion_budget': self.max_tokens,
                'context_compactions': _,
                'slot_wait_ms': waited_ms,
                'slot_policy': 'BOUNDED_FIFO_THREE_NATIVE_WORKERS',
                'duration_ms': round((time.monotonic() - started) * 1000),
                'request_sha256': sha(canonical(payload)),
                'response_sha256': sha(canonical(response)),
                'usage': {key: value for key, value in usage.items()
                          if type(value) is int and value >= 0},
                'model_weights_identity_verified': False}}
        finally:
            self._release_slot(fd, token)
