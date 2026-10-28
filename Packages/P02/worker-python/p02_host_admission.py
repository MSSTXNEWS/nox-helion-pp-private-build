"""NOX P02 -> existing host events.v3 adapter, not a second event bus.

#6 injects authenticated native identity, the existing host event registry and
its actual publisher. Without these inputs admission fails closed. This module
never opens a DB, starts a server, binds WebView2 or controls the UI.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Mapping
from p02_runtime import P02Error
from p02_capabilities import Identity
from p02_chat_bridge import ChatBridge

P02_TYPES = frozenset({
    'chat.start', 'chat.delta', 'chat.complete', 'chat.error', 'chat.sources'
})
RUN_ID = re.compile(r'^[0-9a-f]{32}$')


@dataclass(frozen=True)
class NativeHostBinding:
    """Provided only by trusted native code; never constructed from page JSON."""
    principal: Identity
    verified_user_session: bool
    allowed_host_event_types: frozenset[str]
    route_map: Mapping[str, str]
    publish: Callable[[str, dict], None]


class P02EventRelay:
    def __init__(self, binding: NativeHostBinding):
        if not isinstance(binding, NativeHostBinding) or not isinstance(binding.principal, Identity):
            raise PermissionError('NATIVE_HOST_BINDING_REQUIRED')
        if not binding.verified_user_session or not binding.principal.tenant or not binding.principal.principal:
            raise PermissionError('NATIVE_SESSION_UNVERIFIED')
        if not callable(binding.publish) or not isinstance(binding.allowed_host_event_types, frozenset):
            raise P02Error('EXISTING_EVENT_BRIDGE_REQUIRED')
        if set(binding.route_map) != P02_TYPES:
            raise P02Error('P02_HOST_EVENT_MAP_INCOMPLETE')
        # #6 provides real events.v3 enums/registry; never invent event names.
        if not all(isinstance(binding.route_map[p], str) and
                   binding.route_map[p] in binding.allowed_host_event_types for p in P02_TYPES):
            raise P02Error('EVENT_TYPE_NOT_IN_EXISTING_V3_REGISTRY')
        self._binding = binding
        self._last_run = None
        self._started = False
        self._finished = False

    def relay(self, event: dict) -> None:
        """Map a bounded P02 event into the existing verified publisher.

        This is synchronous and intentional: native host controls backpressure.
        A failed publish raises; we never imply delivery or emit synthetic ACKs.
        """
        if (not isinstance(event, dict) or not isinstance(event.get('type'), str)
                or event['type'] not in P02_TYPES):
            raise P02Error('P02_EVENT_UNSUPPORTED')
        run = event.get('run_id')
        if not isinstance(run, str) or RUN_ID.fullmatch(run) is None:
            raise P02Error('P02_RUN_ID_INVALID')
        if self._last_run is not None and self._last_run != run:
            raise P02Error('EVENT_RUN_MISMATCH')
        kind = event['type']
        if kind == 'chat.start':
            if self._started:
                raise P02Error('DUPLICATE_CHAT_START')
            if (not isinstance(event.get('model'), str) or
                    not 0 < len(event['model']) <= 256):
                raise P02Error('CHAT_START_MODEL_REQUIRED')
        elif not self._started:
            raise P02Error('CHAT_START_REQUIRED')
        if self._finished:
            raise P02Error('CHAT_ALREADY_TERMINATED')
        if kind == 'chat.delta' and not isinstance(event.get('text'), str):
            raise P02Error('CHAT_DELTA_NOT_TEXT')
        if kind == 'chat.sources' and not isinstance(event.get('sources'), list):
            raise P02Error('CHAT_SOURCES_INVALID')
        if kind == 'chat.complete' and (type(event.get('chars')) is not int or
                                        not 0 <= event['chars'] <= 1_000_000):
            raise P02Error('CHAT_COMPLETE_INVALID')
        payload = {k: v for k, v in event.items() if k != 'type'}
        # Native host schemas are explicit, not a generic JSON-to-privilege
        # forwarder. Rejected extra fields cannot become capabilities on V3.
        permitted = {
            'chat.start': {'run_id', 'model'},
            'chat.delta': {'run_id', 'text'},
            'chat.sources': {'run_id', 'sources'},
            'chat.complete': {'run_id', 'chars'},
            'chat.error': {'run_id', 'code', 'detail'},
        }
        if set(payload) - permitted[kind]:
            raise PermissionError('EVENT_PRIVILEGE_FIELDS_FORBIDDEN')
        if kind == 'chat.error':
            if (not isinstance(payload.get('code'), str) or
                    not 0 < len(payload['code']) <= 32 or
                    not isinstance(payload.get('detail'), str) or
                    len(payload['detail']) > 256):
                raise P02Error('CHAT_ERROR_SCHEMA_INVALID')
        if kind == 'chat.sources':
            rows = payload['sources']
            if len(rows) > 20:
                raise P02Error('CHAT_SOURCES_OVER_QUOTA')
            for row in rows:
                if (not isinstance(row, dict) or
                        not {'source_id', 'title'} <= set(row) or
                        set(row) - {'source_id', 'title', 'url'} or
                        not isinstance(row['source_id'], str) or
                        not 0 < len(row['source_id']) <= 128 or
                        not isinstance(row['title'], str) or
                        not 0 < len(row['title']) <= 200 or
                        ('url' in row and
                         (not isinstance(row['url'], str) or len(row['url']) > 2048))):
                    raise P02Error('CHAT_SOURCES_SCHEMA_INVALID')
                if 'url' in row and not ChatBridge._safe_citation_url(row['url']):
                    raise P02Error('CHAT_SOURCE_URL_FORBIDDEN')
        try:
            serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            encoded = serialized.encode('utf-8', errors='strict')
        except (TypeError, ValueError, OverflowError, UnicodeEncodeError) as exc:
            # Lone UTF-16 surrogates can arrive from malformed JSON escapes.
            # Never let a raw UnicodeEncodeError escape the native host relay.
            raise P02Error('P02_EVENT_NOT_SERIALIZABLE') from exc
        if len(encoded) > 65536:
            raise P02Error('P02_EVENT_PAYLOAD_OVER_QUOTA')
        # The JSON bytes above were the checked, size-bounded native wire
        # frame. Publish a detached deep snapshot: the original WebView/worker
        # may mutate nested sources after validation (or the publisher may
        # retain a reference). Never let those mutations bypass citation gates.
        verified_payload = json.loads(encoded.decode('utf-8'))
        mapped = self._binding.route_map[kind]
        self._binding.publish(mapped, verified_payload)
        if kind == 'chat.start':
            self._started, self._last_run = True, run
        if kind in ('chat.complete','chat.error'):
            self._finished = True
