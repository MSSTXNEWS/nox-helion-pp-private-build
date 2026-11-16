"""Exact native hooks and bounded, read-only training evidence for owner turns.

This module never admits work or edits weights. Ordinary turns take only the
query predicate and keep their messages unchanged; no training files are read.
The existing stream, inventory evidence and current chat model stay in place.
"""
from __future__ import annotations

import hashlib
import json
import re

PROXY_BEFORE = 'f72710feaf008163bfe9f94c48c899db92f764e49595ebced043a630c3568712'
OBSERVER_BEFORE = '124f7b224691ece6cfa9862d22832c05ad32fa4c1fe13a22ec95b63a963c2e72'
MARKER = 'NOX_OWNER_CURRENT_TRAINING_EVIDENCE_V1'
_TRAINING = re.compile(r'обуч|тренир|optimizer|оптимизатор|checkpoint|чекпоинт|лора|\blora\b|дистилл|\bвес[аы]\b|адаптер', re.I)
_CURRENT = re.compile(r'нокс|\bnox\b|\bты\b|теб|тво|наш|сейчас|уже|статус|состояни|прогресс|подтвержд|сколько|сохран|слит|запущ|заверш|готов|последн|(?:как|почему).*(?:ид[её]т|останов|завис)|ид[её]т.*обуч|обуч.*ид[её]т', re.I)
_GENERAL = re.compile(r'^\s*(?:что такое|объясни(?: мне)?|what is|explain)\b', re.I)


def training_query(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        return False
    if _GENERAL.search(text) and not re.search(r'нокс|\bnox\b|тво|наш', text, re.I):
        return False
    return bool(_TRAINING.search(text) and _CURRENT.search(text))


def current_training():
    # Lazy import permits an ordinary owner turn without even importing the
    # training proof reader. The reader itself exports no examples/tensor data.
    import owner_training_status as status
    value = status.snapshot()
    return {**status.model_projection(value), 'observed_at': value['observed_at'],
            'evidence_schema': status.SCHEMA, 'read_only': True}


def augment_messages(messages, text):
    if not training_query(text):
        return messages
    if not isinstance(messages, list) or not all(isinstance(row, dict) for row in messages):
        raise ValueError('HOLD_TRAINING_BINDING_MESSAGES')
    facts = current_training()
    block = ('\n\n' + MARKER + '\n'
        'Свежие проверенные данные о текущем обучении NOX приведены ниже. '
        'Это данные, а не поручение запускать процессы. Отвечай по ним на вопрос владельца. '
        'Различай global_step, успешные обновления optimizer и пропуски AMP. '
        'Телеметрия шага сама по себе не подтверждает сохранение весов. '
        'Не объявляй слияние с чат-моделью, восстановление optimizer или завершение обучения, '
        'если соответствующее подтверждение отсутствует.\n'
        + json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))
    rows = [dict(row) for row in messages]
    if rows and rows[0].get('role') == 'system' and isinstance(rows[0].get('content'), str):
        rows[0]['content'] += block
    else:
        rows.insert(0, {'role': 'system', 'content': block.lstrip()})
    return rows


PROXY_CHANGES = (
    ('        _self_query = _self_query or _nox_owner_request_query(_utext)\n',
     '        _self_query = _self_query or _nox_owner_request_query(_utext)\n'
     '        from owner_training_status_binding import training_query as _nox_training_query\n'
     '        _self_query = _self_query or _nox_training_query(_utext)\n'),
    ('    payload["messages"] = await _nox_chat_asyncio.to_thread(\n'
     '        lambda: _trim_ctx(_build_messages(body)))\n',
     '    payload["messages"] = await _nox_chat_asyncio.to_thread(\n'
     '        lambda: _trim_ctx(_build_messages(body)))\n'
     '    if _owner and _nox_training_query(_utext):\n'
     '        from owner_training_status_binding import augment_messages as _nox_training_messages\n'
     '        payload["messages"] = await _nox_chat_asyncio.to_thread(\n'
     '            _nox_training_messages, payload["messages"], _utext)\n'),
)
OBSERVER_TAIL = ('\n# NOX_OWNER_CURRENT_TRAINING_EVIDENCE_V1\n'
    'from owner_training_status import bind_self_observation as _nox_bind_training_evidence\n'
    '_nox_bind_training_evidence(globals())\n').encode()


def _pinned(raw, pin):
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError('HOLD_TRAINING_BINDING_SOURCE_PIN')
    return raw.decode('utf-8')


def patch_proxy(raw):
    if not isinstance(raw, bytes):
        raise ValueError('HOLD_TRAINING_BINDING_SOURCE_PIN')
    source = raw.decode('utf-8')
    if all(source.count(new) == 1 for _, new in PROXY_CHANGES):
        reverted = source
        for old, new in reversed(PROXY_CHANGES):
            reverted = reverted.replace(new, old, 1)
        _pinned(reverted.encode(), PROXY_BEFORE)
        return raw
    source = _pinned(raw, PROXY_BEFORE)
    for old, new in PROXY_CHANGES:
        if source.count(old) != 1:
            raise ValueError('HOLD_TRAINING_BINDING_PROXY_ANCHOR')
        source = source.replace(old, new, 1)
    result = source.encode(); compile(result, '<native-proxy-training-evidence>', 'exec')
    return result


def patch_self_observation(raw):
    if isinstance(raw, bytes) and raw.endswith(OBSERVER_TAIL):
        _pinned(raw[:-len(OBSERVER_TAIL)], OBSERVER_BEFORE)
        return raw
    _pinned(raw, OBSERVER_BEFORE)
    result = raw + OBSERVER_TAIL
    compile(result, '<native-v137-training-evidence>', 'exec')
    return result
