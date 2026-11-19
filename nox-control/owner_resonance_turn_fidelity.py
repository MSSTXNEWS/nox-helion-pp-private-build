"""Compose a reviewed turn-identity guard into the serving Resonance edge."""

from hashlib import sha256

EDGE_PREIMAGE_SHA256 = '4dfc48d178de35c1ba3b6625fd2cd7e2df891b3dac6c515947971e4863a97eeb'

# The four anchors occur only in the deployed Python collector. The public
# page, request store, connection recovery, and native proxy remain untouched.
PRELUDE = """            started = False
            terminal = None
"""
GUARDED_PRELUDE = """            started = False
            preparing = False
            saw_visible_delta = False
            exchange_id = None
            terminal = None

            def unique_fields(pairs):
                fields = {}
                for key, item in pairs:
                    if key in fields:
                        raise ValueError('HOLD_EDGE_DUPLICATE_FRAME_FIELD')
                    fields[key] = item
                return fields

"""
DECODE = """                value = json.loads(line.decode('utf-8'))
                if not isinstance(value, dict):
                    raise ValueError('HOLD_EDGE_STREAM_FRAME')
                kind = value.get('type')
                if kind == 'preparing' and not started:
"""
GUARDED_DECODE = """                value = json.loads(line.decode('utf-8'), object_pairs_hook=unique_fields)
                if not isinstance(value, dict):
                    raise ValueError('HOLD_EDGE_STREAM_FRAME')
                # Legacy native phase/delta events need not echo turn IDs.
                # An explicit ID must match this request-bound connection.
                if any(key in value and value[key] != expected
                       for key, expected in self.binding.items()):
                    raise ValueError('HOLD_EDGE_FRAME_BINDING')
                if 'exchange_id' in value:
                    native_exchange = value['exchange_id']
                    if (not isinstance(native_exchange, str)
                            or not (S03_ID.fullmatch(native_exchange) or ID.fullmatch(native_exchange))
                            or (exchange_id is not None and native_exchange != exchange_id)):
                        raise ValueError('HOLD_EDGE_EXCHANGE_BINDING')
                    exchange_id = native_exchange
                kind = value.get('type')
                if kind == 'preparing' and not started and not preparing:
                    preparing = True
"""
DELTA = """                elif kind == 'delta' and started and isinstance(value.get('text'), str):
                    self.append('delta', text=value['text'])
"""
GUARDED_DELTA = """                elif kind == 'delta' and started and isinstance(value.get('text'), str):
                    saw_visible_delta = saw_visible_delta or bool(value['text'].strip())
                    self.append('delta', text=value['text'])
"""
DONE = """                elif kind == 'done' and started:
                    # This is the only upstream response for this turn. The
"""
GUARDED_DONE = """                elif kind == 'done' and started and saw_visible_delta:
                    # This is the only upstream response for this turn. The
"""


def _patch_collector(source: str) -> str:
    start = source.index('    def collect(self, upstream):\n')
    stop = source.index('\n\nclass TurnStore:', start)
    collector = source[start:stop]
    for old, new in (
        (PRELUDE, GUARDED_PRELUDE),
        (DECODE, GUARDED_DECODE),
        (DELTA, GUARDED_DELTA),
        (DONE, GUARDED_DONE),
    ):
        if collector.count(old) != 1:
            raise ValueError('HOLD_EDGE_FIDELITY_ANCHOR')
        collector = collector.replace(old, new, 1)
    return source[:start] + collector + source[stop:]


def transform_turn_fidelity(raw: bytes, *, reviewed_sha256: str = EDGE_PREIMAGE_SHA256) -> bytes:
    """Patch the deployed source or an explicitly pinned compatible composition."""
    if not isinstance(raw, bytes) or sha256(raw).hexdigest() != reviewed_sha256:
        raise ValueError('HOLD_EDGE_FIDELITY_PREIMAGE')
    candidate = _patch_collector(raw.decode('utf-8')).encode('utf-8')
    compile(candidate, 'owner_resonance_gateway.py', 'exec')
    return candidate
