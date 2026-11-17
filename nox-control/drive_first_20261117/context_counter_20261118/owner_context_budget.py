"""Bounded request-local context accounting for the selected NOX backend.

Counts cover rendered messages at this call, not later tools/enrichments. No
cross-request cache, model invocation, weight reads, context-window expansion
or truncation of the original latest user question or stable instructions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 524288
MAX_PROMPT_BYTES = 262144
MAX_TOKENS = 65536
MAX_MESSAGES = 64
MAX_ROUNDS = 2
TIME_BUDGET = 1.2
PHASE_TIMEOUT = .35
DEFAULT_CHAR_BUDGET = 2048
TOOLS_RESERVE = 1300  # Preserve the existing policy; not a measured tool count.
CONTRACT_MARK = 'NOX VERIFIED SELF-MODEL CONTRACT:'


class Unavailable(RuntimeError):
    pass


class ProtectedContextTooLarge(RuntimeError):
    """A valid measurement exceeds policy allowance for protected text alone."""


def _require(value, reason):
    if not value:
        raise Unavailable(reason)


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, 'DUPLICATE_JSON_FIELD')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(Unavailable('NONFINITE_JSON')))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _base(url):
    try:
        value = urlsplit(url)
        if (value.scheme != 'http' or value.hostname not in ('127.0.0.1', 'localhost')
                or value.port not in (8098, 8085) or value.username is not None
                or value.password is not None or value.query or value.fragment
                or value.path != '/v1/chat/completions'):
            return None
        return 'http://' + value.netloc
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Count:
    tokens: int | None
    reason: str
    prompt_sha256: str | None = None
    cached: bool = False

    @property
    def known(self):
        return self.tokens is not None


class Session:
    """One selected URL, two count rounds, one cooperative wall budget.

Only counts keyed by an actually rendered prompt are reused. Every round
renders again, so a changed template does not reuse its old prompt's count.
Backend process/tokenizer identity is not observed: this cache never survives
the current request and does not claim an atomic backend-generation snapshot.
"""
    def __init__(self, selected_url, *, transport=None, clock=time.monotonic):
        self.base = _base(selected_url)
        self.clock = clock
        self.deadline = clock() + TIME_BUDGET
        self.transport = transport
        self.rounds = 0
        self.requests = 0
        self.count_cache = {}
        self.client = None
        self.context_reason = 'NOT_OBSERVED'

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None

    def remaining(self):
        remaining = self.deadline - self.clock()
        _require(remaining > 0, 'TIME_BUDGET_EXHAUSTED')
        return remaining

    def _http(self, method, url, payload, timeout):
        import httpx
        if self.client is None:
            self.client = httpx.Client(trust_env=False, follow_redirects=False)
        kwargs = {'timeout': httpx.Timeout(timeout, connect=min(timeout, .15),
                  read=timeout, write=min(timeout, .15), pool=min(timeout, .15)),
                  'headers': {'Accept-Encoding': 'identity'}}
        if payload is not None:
            kwargs['json'] = payload
        with self.client.stream(method, url, **kwargs) as response:
            _require(response.status_code == 200, 'TOKENIZER_HTTP_STATUS')
            _require(response.headers.get('Content-Encoding', '').lower() in ('', 'identity'),
                     'TOKENIZER_RESPONSE_ENCODING')
            raw = bytearray()
            for chunk in response.iter_raw():
                self.remaining()
                _require(len(raw) + len(chunk) <= MAX_RESPONSE_BYTES, 'RESPONSE_BYTES')
                raw.extend(chunk)
        return bytes(raw)

    def request(self, method, endpoint, payload=None):
        _require(self.base is not None, 'SELECTED_ROUTE_UNSUPPORTED')
        _require((method, endpoint) in (('GET', '/slots'), ('POST', '/apply-template'),
                    ('POST', '/tokenize')), 'TOKENIZER_REQUEST_SCOPE')
        _require(self.requests < 5, 'HTTP_REQUEST_LIMIT')
        timeout = min(PHASE_TIMEOUT, self.remaining())
        self.requests += 1
        operation = self.transport or self._http
        raw = operation(method, self.base + endpoint, payload, timeout)
        self.remaining()
        _require(isinstance(raw, bytes) and len(raw) <= MAX_RESPONSE_BYTES, 'RESPONSE_BYTES')
        return _json(raw)

    def slot_context(self):
        try:
            slots = self.request('GET', '/slots')
            _require(isinstance(slots, list) and 1 <= len(slots) <= 16, 'SLOT_SCHEMA')
            contexts = [row.get('n_ctx') if isinstance(row, dict) else None for row in slots]
            _require(all(type(n) is int and 256 <= n <= 1048576 for n in contexts), 'SLOT_CONTEXT_UNKNOWN')
            self.context_reason = 'MIN_OBSERVED_SELECTED_ROUTE_SLOT_CONTEXT'
            return min(contexts)
        except Exception as error:
            self.context_reason = str(error) if isinstance(error, Unavailable) else 'SLOT_READ_UNAVAILABLE'
            return None

    def measure(self, messages):
        if self.rounds >= MAX_ROUNDS:
            return Count(None, 'TOKENIZER_ROUND_LIMIT')
        self.rounds += 1
        try:
            _require(isinstance(messages, list) and len(messages) <= MAX_MESSAGES, 'MESSAGES_SCHEMA')
            message_raw = _canonical(messages)
            _require(len(message_raw) <= MAX_PROMPT_BYTES, 'MESSAGE_BYTES')
            message_hash = hashlib.sha256(message_raw).hexdigest()
            rendered = self.request('POST', '/apply-template', {'messages': messages})
            _require(isinstance(rendered, dict) and isinstance(rendered.get('prompt'), str), 'TEMPLATE_SCHEMA')
            prompt = rendered['prompt']
            _require(prompt != '' or messages == [], 'TEMPLATE_EMPTY_FOR_MESSAGES')
            prompt_raw = prompt.encode()
            _require(len(prompt_raw) <= MAX_PROMPT_BYTES, 'PROMPT_BYTES')
            prompt_hash = hashlib.sha256(prompt_raw).hexdigest()
            key = self.base, message_hash, prompt_hash
            if key in self.count_cache:
                return Count(self.count_cache[key], 'RENDERED_PROMPT_REQUEST_CACHE', prompt_hash, True)
            value = self.request('POST', '/tokenize', {'content': prompt})
            _require(isinstance(value, dict) and isinstance(value.get('tokens'), list), 'TOKENS_SCHEMA')
            tokens = value['tokens']
            _require(len(tokens) <= MAX_TOKENS and all(type(n) is int and 0 <= n <= 2147483647 for n in tokens),
                     'TOKEN_IDS_SCHEMA')
            _require(bool(tokens) or prompt == '', 'EMPTY_TOKENS_FOR_NONEMPTY_PROMPT')
            count = len(tokens)
            self.count_cache[key] = count
            return Count(count, 'MEASURED_RENDERED_MESSAGE_TEMPLATE', prompt_hash)
        except Exception as error:
            reason = str(error) if isinstance(error, Unavailable) else 'TOKENIZER_UNAVAILABLE'
            return Count(None, reason)


def count_messages(messages, selected_url=None, *, session=None):
    owned = session is None
    active = session or Session(selected_url)
    try:
        # Never silently switch a shared counting session to another backend.
        if selected_url is not None and _base(selected_url) != active.base:
            return Count(None, 'SELECTED_ROUTE_SESSION_MISMATCH')
        return active.measure(messages)
    finally:
        if owned:
            active.close()


def _chars(messages):
    return sum(len(row['content']) for row in messages)


def _stable_system(row):
    result = dict(row)
    value = row['content']
    # This seam is generated by actual _build_messages. If its shape is not
    # uniquely recognisable, keep the entire system message, never cut it.
    if value.count(CONTRACT_MARK) == 1:
        index = value.find(CONTRACT_MARK) + len(CONTRACT_MARK)
        tail = value.find('\n\n', index)
        if tail >= 0:
            result['content'] = value[:tail]
    return result


def _parts(messages, original_user_text):
    if (not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES
            or any(not isinstance(row, dict) or not isinstance(row.get('content'), str)
                   or row.get('role') not in ('system', 'user', 'assistant', 'tool', 'function') for row in messages)):
        return None
    rows = [dict(row) for row in messages]
    first = 0
    while first < len(rows) and rows[first]['role'] == 'system':
        first += 1
    if any(row['role'] == 'system' for row in rows[first:]):
        return None
    indexes = [i for i in range(first, len(rows)) if rows[i]['role'] == 'user']
    if not indexes or rows[first]['role'] != 'user':
        return None
    last = indexes[-1]
    groups = [rows[a:b] for a, b in zip(indexes[:-1], indexes[1:])]
    tail = rows[last:]
    protected_tail = [dict(row) for row in tail]
    if isinstance(original_user_text, str):
        protected_tail[0]['content'] = original_user_text
        if original_user_text not in tail[0]['content']:
            tail[0]['content'] = (original_user_text + '\n\nДополнение NOX (справочные данные):\n'
                                  + tail[0]['content'])
    system = rows[:first]
    stable = [_stable_system(row) for row in system]
    return system, stable, groups, tail, protected_tail


def _flatten(system, groups, tail):
    return [dict(row) for row in system] + [dict(row) for group in groups for row in group] + [dict(row) for row in tail]


def _plan(parts, target_chars):
    system, stable, groups, tail, protected_tail = parts
    kept = list(groups)
    candidate = _flatten(system, kept, tail)
    while kept and _chars(candidate) > target_chars:
        kept.pop(0)
        candidate = _flatten(system, kept, tail)
    if _chars(candidate) > target_chars:
        candidate = _flatten(stable, kept, tail)
    if _chars(candidate) > target_chars:
        candidate = _flatten(stable, kept, protected_tail)
    return candidate


@dataclass
class TrimResult:
    messages: list
    assessment: dict


def trim_messages(messages, *, selected_url, original_user_text=None, output_tokens=None,
                  char_budget=None, session=None):
    parts = _parts(messages, original_user_text)
    if parts is None:
        return TrimResult(messages, {'status': 'UNCHANGED_UNSUPPORTED_MESSAGE_SHAPE', 'final_message_tokens': None,
                                    'exact_final_context_fit': False})
    owned = session is None
    active = session or Session(selected_url)
    info = {'status': 'UNMEASURED', 'final_message_tokens': None, 'exact_final_context_fit': False,
        'count_scope': 'RENDERED_MESSAGES_BEFORE_LATER_TOOLS_AND_ENRICHMENTS',
        'backend_generation_observed': False, 'cross_request_cache': False,
        'protected_latest_original_question': isinstance(original_user_text, str),
        'stable_instructions_truncated': False, 'time_budget_kind': 'COOPERATIVE_WITH_SOCKET_PHASE_TIMEOUTS'}
    try:
        if _base(selected_url) != active.base:
            return TrimResult(messages, info | {'status': 'UNCHANGED_SESSION_ROUTE_MISMATCH'})
        context = active.slot_context()
        reserve = max(512, output_tokens) if type(output_tokens) is int and 1 <= output_tokens <= 65536 else 512
        allowance = context - reserve - TOOLS_RESERVE if context is not None else None
        info.update(selected_route_slot_context=context, context_reason=active.context_reason,
                    output_reserve=reserve, tool_reserve_policy=TOOLS_RESERVE,
                    message_allowance=allowance)
        target = char_budget if type(char_budget) is int and char_budget >= 0 else None
        full = _flatten(parts[0], parts[2], parts[3])
        minimum = _flatten(parts[1], [], parts[4])
        candidate = _plan(parts, target) if target is not None else full
        if allowance is None:
            # An unknown window is not a reason to borrow primary8098 context
            # for fallback8085 or to force a new mandatory-tokenizer gate.
            candidate = _plan(parts, DEFAULT_CHAR_BUDGET if target is None else target)
            info.update(status='HEURISTIC_ONLY_CONTEXT_UNAVAILABLE', heuristic_char_budget=
                        DEFAULT_CHAR_BUDGET if target is None else target)
            return TrimResult(candidate, info)
        if allowance <= 0:
            raise ProtectedContextTooLarge('CONTEXT_RESERVES_EXCEED_OBSERVED_SLOT_POLICY')
        measured = count_messages(candidate, selected_url, session=active)
        if not measured.known:
            fallback = min(target, allowance * 2) if target is not None else allowance * 2
            candidate = _plan(parts, fallback)
            info.update(status='HEURISTIC_ONLY_TOKENIZER_UNAVAILABLE', count_reason=measured.reason,
                        heuristic_char_budget=fallback)
            return TrimResult(candidate, info)
        if measured.tokens <= allowance:
            info.update(status='MEASURED_MESSAGES_WITHIN_POLICY_ALLOWANCE', final_message_tokens=measured.tokens,
                        count_reason=measured.reason, rendered_prompt_sha256=measured.prompt_sha256)
            return TrimResult(candidate, info)
        if candidate == minimum:
            raise ProtectedContextTooLarge('PROTECTED_MESSAGES_EXCEED_OBSERVED_SLOT_POLICY_ALLOWANCE')
        # One bulk correction, then at most one final count round. History is
        # removed as whole user-led groups, including their tool call/results.
        target = max(0, int(_chars(candidate) * allowance / measured.tokens * .85))
        candidate = _plan(parts, target)
        final = count_messages(candidate, selected_url, session=active)
        if final.known and final.tokens > allowance:
            if candidate == minimum:
                raise ProtectedContextTooLarge('PROTECTED_MESSAGES_EXCEED_OBSERVED_SLOT_POLICY_ALLOWANCE')
            # Do not call a third tokenizer round or claim the final minimum
            # has the preceding candidate's count. The backend validates it.
            candidate = minimum
            info.update(status='UNMEASURED_PROTECTED_ONLY_AFTER_TWO_ROUNDS', count_reason='FINAL_PAYLOAD_CHANGED_AFTER_COUNT')
        elif final.known:
            info.update(status='MEASURED_MESSAGES_WITHIN_POLICY_ALLOWANCE', final_message_tokens=final.tokens,
                        count_reason=final.reason, rendered_prompt_sha256=final.prompt_sha256)
        else:
            info.update(status='HEURISTIC_ONLY_FINAL_COUNT_UNAVAILABLE', count_reason=final.reason,
                        heuristic_char_budget=target)
        return TrimResult(candidate, info)
    finally:
        info.update(tokenizer_rounds=active.rounds, helper_http_attempts=active.requests,
                    max_tokenizer_rounds=MAX_ROUNDS, helper_time_budget_seconds=TIME_BUDGET)
        if owned:
            active.close()
