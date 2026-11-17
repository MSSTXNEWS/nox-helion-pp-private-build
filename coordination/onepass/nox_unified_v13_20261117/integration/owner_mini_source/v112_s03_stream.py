"""Source adapter between V38 AttachedNOX and the existing V112 wire format."""
from collections.abc import Callable, Iterator, Mapping
import re
from typing import Any


_DIALOG = re.compile(r'[a-f0-9]{32}\Z')
_TURN = re.compile(r'[A-Za-z0-9._:-]{1,100}\Z')
_MODEL = 'NOX HELION'
_STREAM_MODE = 'NATIVE_TOKEN_STREAM'
_MAX_ANSWER = 2_000_000


class _Hold(RuntimeError):
    pass


def _identity(value: Any, *, minimum: int = 1, maximum: int = 160) -> bool:
    return isinstance(value, str) and minimum <= len(value) <= maximum and all(
        ord(char) >= 32 and ord(char) != 127 for char in value
    )


def _check_readback(
    proof: Mapping,
    *,
    dialog_id: str,
    turn_id: str,
    receipt_id: str,
    prompt: str,
    answer: str,
) -> str:
    if (
        not isinstance(proof, Mapping)
        or proof.get('dialog_id') != dialog_id
        or proof.get('turn_id') != turn_id
        or proof.get('receipt_id') != receipt_id
        or proof.get('status') != 'READY'
    ):
        raise _Hold('HOLD_S03_DURABLE_TURN_READBACK')
    exchange_id = proof.get('exchange_id')
    history = proof.get('messages')
    if (
        not _identity(exchange_id, minimum=6)
        or not isinstance(history, (list, tuple))
        or len(history) > 100
    ):
        raise _Hold('HOLD_S03_DIALOG_COMMIT_NOT_VERIFIED')
    pair = [row for row in history if isinstance(row, Mapping) and row.get('exchange_id') == exchange_id]
    if len(pair) != 2 or (
        (pair[0].get('role'), pair[0].get('content')),
        (pair[1].get('role'), pair[1].get('content')),
    ) != (('user', prompt), ('assistant', answer)):
        raise _Hold('HOLD_S03_DIALOG_COMMIT_NOT_VERIFIED')
    return exchange_id


def stream_v112_turn(
    attached,
    session,
    prompt: str,
    turn_id: str,
    *,
    still_authorized: Callable[[], bool],
    readback: Callable[[str, str, str], Mapping],
) -> Iterator[dict]:
    """Project V38 events to V112 without creating a model call or S03 writer.

    The host binds the trusted session and live STOP/ACL fence. The read-only
    callback reads a bridge proof and exact V112 history from the existing S03.
    """
    events = None

    def check_fence():
        if still_authorized() is not True:
            raise _Hold('STREAM_STOP_REQUESTED')

    try:
        session.validate()
        dialog_id = session.chat_id
        if (
            not _DIALOG.fullmatch(dialog_id)
            or not isinstance(turn_id, str)
            or not _TURN.fullmatch(turn_id)
            or not isinstance(prompt, str)
            or not 1 <= len(prompt.strip()) <= 8000
            or len(prompt) > 8000
        ):
            raise _Hold('HOLD_V112_TURN_CONTRACT')
        check_fence()
        yield {'type': 'preparing', 'stream_mode': _STREAM_MODE}
        events = iter(attached.stream(session, prompt, turn_id))
        cortex_ready = False
        part_count = 0
        answer_parts = []
        answer_chars = 0
        receipt_id = None
        while True:
            check_fence()
            try:
                frame = next(events)
            except StopIteration:
                break
            check_fence()
            if receipt_id is not None or not isinstance(frame, Mapping):
                raise _Hold('HOLD_S03_STREAM_ORDER')
            kind = frame.get('type')
            if kind == 'phase':
                continue
            if kind == 'hold':
                raise _Hold('HOLD_S03_NATIVE_TURN')
            if kind == 'cortex_ready':
                if cortex_ready or part_count:
                    raise _Hold('HOLD_S03_STREAM_ORDER')
                cortex_ready = True
                continue
            if kind == 'delta':
                text = frame.get('text')
                seq = frame.get('seq')
                if (
                    not cortex_ready or not isinstance(text, str) or not text
                    or not _identity(frame.get('evidence_receipt'))
                    or type(seq) is not int or seq != part_count + 1
                    or answer_chars + len(text) > _MAX_ANSWER
                ):
                    raise _Hold('HOLD_S03_DURABLE_DELTA')
                answer_parts.append(text)
                answer_chars += len(text)
                part_count += 1
                if part_count == 1:
                    yield {'type': 'start', 'model': _MODEL, 'stream_mode': _STREAM_MODE}
                    check_fence()
                yield {'type': 'delta', 'text': text}
                continue
            if kind == 'done' and (
                frame.get('state') == 'S03_DURABLE_TURN'
                and _identity(frame.get('receipt'))
                and type(frame.get('output_chars')) is int
                and frame['output_chars'] == answer_chars
                and part_count
            ):
                receipt_id = frame['receipt']
                continue
            raise _Hold('HOLD_S03_STREAM_ORDER')
        if not receipt_id:
            raise _Hold('HOLD_S03_COMMIT_NOT_VERIFIED')
        check_fence()
        proof = readback(dialog_id, turn_id, receipt_id)
        exchange_id = _check_readback(
            proof, dialog_id=dialog_id, turn_id=turn_id, receipt_id=receipt_id,
            prompt=prompt, answer=''.join(answer_parts),
        )
        check_fence()
        yield {'type': 'done', 'model': _MODEL, 'saved': True, 's03_integrated': True,
               'dialog_id': dialog_id, 'exchange_id': exchange_id, 'stream_mode': _STREAM_MODE}
    except _Hold as exc:
        yield {'type': 'error', 'error': str(exc)}
    except Exception:
        yield {'type': 'error', 'error': 'HOLD_S03_HOST_ADAPTER'}
    finally:
        close = getattr(events, 'close', None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
