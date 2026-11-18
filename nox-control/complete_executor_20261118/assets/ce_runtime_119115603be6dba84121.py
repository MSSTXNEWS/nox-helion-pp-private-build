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
import os
from pathlib import Path
import stat
import time
import urllib.error
import urllib.request

from owner_project_planner import PlannerHold, canonical, require, sha

BASE_URL = 'http://127.0.0.1:8098'
MODEL_LOCK = Path('/root/nox/state/dispatcher/project_model_slot.lock')
MAX_REPLY = 256 * 1024


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

    def _slot_lock(self):
        path = self.lock_path
        require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)),
                'MODEL_LOCK_PATH')
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if not (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_nlink == 1):
            os.close(fd)
            raise PlannerHold('HOLD_PROJECT_MODEL_LOCK_OWNER')
        start = time.monotonic()
        try:
            while True:
                self._alive()
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fd
                except BlockingIOError:
                    require(time.monotonic() - start < 120, 'MODEL_SLOT_BUSY')
                    time.sleep(.5)
        except BaseException:
            os.close(fd)
            raise

    def __call__(self, messages):
        self._alive()
        fd = self._slot_lock()
        try:
            models = self.http('/v1/models')
            require(isinstance(models, dict) and isinstance(models.get('data'), list)
                    and any(isinstance(x, dict) and x.get('id') == self.model_id
                            for x in models['data']), 'MODEL_ID_CHANGED')
            props = self.http('/props')
            settings = props.get('default_generation_settings') if isinstance(props, dict) else None
            context = settings.get('n_ctx') if isinstance(settings, dict) else None
            require(type(context) is int and context >= 2048, 'MODEL_CONTEXT_UNKNOWN')
            slot_deadline = time.monotonic() + 120
            while True:
                self._alive()
                slots = self.http('/slots')
                require(isinstance(slots, list) and len(slots) >= 2, 'MODEL_SLOT_SCHEMA')
                if any(isinstance(s, dict) and s.get('is_processing') is False for s in slots):
                    break
                require(time.monotonic() < slot_deadline, 'MODEL_NO_AVAILABLE_SLOT')
                time.sleep(.5)
            current = copy.deepcopy(messages)
            for _ in range(24):
                self._alive()
                rendered = self.http('/apply-template', {'messages': current})
                require(isinstance(rendered, dict) and isinstance(rendered.get('prompt'), str),
                        'MODEL_TEMPLATE_SCHEMA')
                tokenized = self.http('/tokenize', {'content': rendered['prompt'],
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
            response = self.http('/v1/chat/completions', payload, timeout=180)
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
                'duration_ms': round((time.monotonic() - started) * 1000),
                'request_sha256': sha(canonical(payload)),
                'response_sha256': sha(canonical(response)),
                'usage': {key: value for key, value in usage.items()
                          if type(value) is int and value >= 0},
                'model_weights_identity_verified': False}}
        finally:
            os.close(fd)
