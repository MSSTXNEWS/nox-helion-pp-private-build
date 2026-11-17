"""Bounded parsing of the installed V24 SSE contract, with safe receipts.

This module has no HTTP, model, subprocess or native-app imports. A token frame
is a transport event, not a model token; its bound must never be reported as a
generation-token limit. The native adapter remains blocked until that separate
source-derived limit and the actual dialog persistence contract are verified.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import time

S03_MARKER = 'FULL_QUESTION_AND_ANSWER_SUBSTRINGS'
S03_PROOF = 'M1_LENGTH_FRAMED_V2_SHA256'
REQUEST_MAX_TOKENS = 256
OLD_OWNED_DIALOG = '5ce69137da0a4c42a0387917c8567d52'
MAX_STREAM_BYTES = 65536
MAX_LINE_BYTES = 16384
MAX_CONTENT_BYTES = 4096
MAX_TOKEN_FRAMES = 512
MAX_LINES = 4096
WALL_SECONDS = 90.0


class Hold(RuntimeError):
    """Fixed codes only; HTTP bodies and private model text are never errors."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, code):
    if not condition:
        raise Hold(code)


def synthetic_question(nonce):
    require(isinstance(nonce, str) and re.fullmatch('[a-f0-9]{32}', nonce), 'HOLD_NONCE')
    # Existing _infinite_persist recognizes this exact test tag. No user data.
    marker = '[t690u-test][NOX_V24_CANCEL_' + nonce + ']'
    return marker + (' Синтетическая проверка отмены. Опиши в четырёх коротких '
        'предложениях, как меняется восприятие знакомого пейзажа при разном '
        'освещении. Ответь по существу; внешние действия не требуются.')


def own_body(nonce, dialog_id):
    require(isinstance(dialog_id, str) and re.fullmatch('[a-f0-9]{32}', dialog_id)
            and dialog_id != OLD_OWNED_DIALOG, 'HOLD_FRESH_DIALOG_REQUIRED')
    return {'message': synthetic_question(nonce), 'history': [], 'dialog_id': dialog_id,
            'request_id': 'p0-' + nonce, 'max_tokens': REQUEST_MAX_TOKENS}


@dataclass(frozen=True)
class Turn:
    answer: str
    dialog_id: str
    exchange_id: str
    record_sha256: str
    received_bytes: int
    content_bytes: int
    token_frames: int
    placeholder_frames: int
    first_content_ms: int
    first_nonplaceholder_ms: int
    completed_ms: int

    def safe_receipt(self):
        # No answer, question, arbitrary frame fields, URL or raw error text.
        return {'schema': 'NOX_P0_V24_STREAM_OBSERVATION_V1',
            'answer_sha256': digest(self.answer.encode('utf-8')),
            'dialog_id': self.dialog_id, 'exchange_id': self.exchange_id,
            's03_readback': S03_MARKER, 'stream_exhausted': True,
            's03_proof': S03_PROOF, 's03_record_sha256': self.record_sha256,
            'received_bytes': self.received_bytes, 'content_bytes': self.content_bytes,
            'token_frames': self.token_frames, 'placeholder_frames': self.placeholder_frames,
            'first_content_ms': self.first_content_ms,
            'first_nonplaceholder_ms': self.first_nonplaceholder_ms,
            'completed_ms': self.completed_ms,
            'generation_tokens_observed': None,
            'token_frames_are_not_generation_tokens': True,
            'semantic_answer_review': 'PENDING',
            'native_model_path_verified': False,
            'durable_history_verified': False,
            'independent_s03_record_verified': False,
            'used': False, 'accepted': False}


def read_v24(response, dialog_id, started, *, clock=time.monotonic):
    """Read to normal EOF, never treating an early done/header as completion.

    The caller must also enforce an interruptible whole-operation deadline.
    These clock checks alone cannot interrupt a blocked socket read.
    """
    require(isinstance(dialog_id, str) and re.fullmatch('[a-f0-9]{32}', dialog_id)
            and dialog_id != OLD_OWNED_DIALOG, 'HOLD_FRESH_DIALOG_REQUIRED')
    total = content_bytes = token_frames = placeholder_frames = 0
    first_content = first_nonplaceholder = None
    terminal = None
    saw_context = saw_meta = False
    frame_data = None
    parts = []

    def elapsed():
        seconds = clock() - started
        require(0 <= seconds < WALL_SECONDS, 'HOLD_CANARY_WALL_DEADLINE')
        return round(seconds * 1000)

    for _ in range(MAX_LINES):
        elapsed()
        line = response.readline(min(MAX_LINE_BYTES + 1, MAX_STREAM_BYTES - total + 1))
        at = elapsed()
        require(isinstance(line, bytes), 'HOLD_SSE_BYTES_REQUIRED')
        if not line:
            require(frame_data is None, 'HOLD_SSE_UNTERMINATED_FRAME')
            break
        total += len(line)
        require(total <= MAX_STREAM_BYTES, 'HOLD_SSE_STREAM_BYTES')
        require(len(line) <= MAX_LINE_BYTES, 'HOLD_SSE_LINE_BYTES')
        require(line.endswith(b'\n'), 'HOLD_SSE_UNTERMINATED_LINE')
        try:
            value = line[:-1].removesuffix(b'\r').decode('utf-8', 'strict')
        except UnicodeDecodeError:
            raise Hold('HOLD_SSE_UTF8') from None
        if value.startswith(':'):
            continue
        if value:
            require(terminal is None, 'HOLD_SSE_DATA_AFTER_DONE')
            require(value.startswith('data:'), 'HOLD_SSE_FIELD')
            require(frame_data is None, 'HOLD_V24_MULTILINE_DATA')
            frame_data = value[5:].lstrip(' ')
            continue
        if frame_data is None:
            continue
        try:
            frame = json.loads(frame_data)
        except (ValueError, RecursionError):
            raise Hold('HOLD_SSE_JSON') from None
        frame_data = None
        require(isinstance(frame, dict), 'HOLD_SSE_OBJECT')
        kind = frame.get('type')
        require(kind in ('context', 'meta', 'token', 'done', 'error'), 'HOLD_V24_FRAME_TYPE')
        if kind == 'context':
            require(not saw_context and not saw_meta and not token_frames, 'HOLD_V24_CONTEXT_ORDER')
            saw_context = True
        elif kind == 'meta':
            require(saw_context and not saw_meta and not token_frames
                    and frame.get('dialog_id') == dialog_id, 'HOLD_V24_DIALOG_BINDING')
            saw_meta = True
        elif kind == 'token':
            require(saw_context and saw_meta, 'HOLD_V24_TOKEN_ORDER')
            part = frame.get('t')
            require(isinstance(part, str) and bool(part), 'HOLD_V24_TOKEN_SCHEMA')
            encoded = part.encode('utf-8')
            content_bytes += len(encoded)
            token_frames += 1
            require(content_bytes <= MAX_CONTENT_BYTES, 'HOLD_CONTENT_BYTES')
            require(token_frames <= MAX_TOKEN_FRAMES, 'HOLD_TOKEN_FRAME_COUNT')
            if first_content is None:
                first_content = at
            if any(character.isalpha() or character.isdigit() for character in part):
                if first_nonplaceholder is None:
                    first_nonplaceholder = at
            else:
                placeholder_frames += 1
            parts.append(part)
        elif kind == 'error':
            raise Hold('HOLD_V24_REPORTED_ERROR')
        else:
            require(saw_context and saw_meta and first_nonplaceholder is not None,
                    'HOLD_V24_NO_NONPLACEHOLDER_CONTENT')
            require(frame.get('status') == 'done' and frame.get('saved') is True
                    and frame.get('s03_integrated') is True and frame.get('s03_readback') == S03_MARKER
                    and frame.get('s03_proof') == S03_PROOF,
                    'HOLD_P0_S03_MARKER')
            exchange = frame.get('exchange_id')
            require(isinstance(exchange, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{6,128}', exchange),
                    'HOLD_S03_EXCHANGE_ID')
            record_sha = frame.get('s03_record_sha256')
            require(isinstance(record_sha, str) and re.fullmatch('[a-f0-9]{64}', record_sha),
                    'HOLD_S03_RECORD_DIGEST')
            terminal = exchange, record_sha
    else:
        raise Hold('HOLD_SSE_LINE_COUNT')
    require(terminal is not None, 'HOLD_V24_MISSING_DONE')
    answer = ''.join(parts)
    require(len(answer.strip()) >= 2, 'HOLD_V24_EMPTY_CONTENT')
    return Turn(answer, dialog_id, terminal[0], terminal[1], total, content_bytes, token_frames,
                placeholder_frames, first_content, first_nonplaceholder, elapsed())
