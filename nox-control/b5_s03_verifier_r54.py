"""B5 R54 isolated S03 verifier port; NO live I/O or admission.
Exact R53 source 148672b8d57828f5063546bec6b4df3520cca189, blob 83fc539b47821bb2f7f1aa5ce18086b342e78d3b.
Main QA remains untouched; independent trusted pins required. Run this file for synthetic tests only.
"""
import hashlib
import json
import math
import re
import unittest

def digest(data):
    return hashlib.sha256(data).hexdigest()


def distinct_explicit_message_ids(rows):
    """Optional row IDs must not claim multiple distinct turns with one identity.

    Historical S03/dialog-history responses may omit message_id; whenever
    an ID is explicitly supplied it must be a nonblank string and unique.
    """
    ids = [row['message_id'] for row in rows if 'message_id' in row]
    # A nonblank but padded or invisible identifier is not durable row
    # provenance. Reject it at the FIRST owner-history gate, before any
    # Spanish follow-up; preserve valid Unicode and legacy absent IDs.
    return (all(isinstance(mid, str) and bool(mid)
                and mid == mid.strip() and mid.isprintable() for mid in ids)
            and len(ids) == len(set(ids)))


def multiturn_transcript_sha256(rows, *, expected_sequence=2, _prefix_only=False):
    """Fingerprint full UTF-8 browser-history messages, not S03 proof.

    Canonical writer provenance still requires a separate trusted receipt
    and independent readback. Never truncate or normalize message content.
    """
    if (type(expected_sequence) is not int
            or expected_sequence not in ((1,) if _prefix_only is True else (2, 3))):
        return None
    roles = ('user', 'assistant') * expected_sequence
    if not isinstance(rows, list) or len(rows) != len(roles):
        return None
    if any(not isinstance(row, dict) or row.get('role') != role
           or not isinstance(row.get('content'), str) or not row['content'].strip()
           for row, role in zip(rows, roles)):
        return None
    # Owner browser-history JSON reads are bounded to 200000 bytes by
    # json_response(). An oversized witness cannot be independently read
    # through that route. Reject it; never truncate or normalize RU/ES text.
    if any(len(row['content']) > 200000 for row in rows):
        return None
    transcript = [{'role': role, 'content': row['content']}
                  for row, role in zip(rows, roles)]
    try:
        # API JSON may contain a lone escaped UTF-16 surrogate. Such text
        # cannot be persisted as strict UTF-8; it must never certify an S03
        # transcript or abort the owner QA with an uncategorized codec error.
        raw = json.dumps(transcript, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    except UnicodeEncodeError:
        return None
    if len(raw) > 200000:
        return None
    return digest(raw)


def canonical_s03_proof_valid(writer_receipt, independent_readback, dialog_id, expected_messages,
                              require_full_transcript_pin=False, *, expected_sequence=2,
                              _prefix_only=False):
    """Match independent S03 witnesses; strict B5 requires full transcript pins.

    The legacy A1 source contract does not include full_transcript_sha256.
    Preserve that source-only compatibility, never treat it as a strict
    two-turn RU/ES acceptance witness. A live B5 verifier must opt in.
    """
    # A single native chat exchange is not a two-turn continuity witness.
    # Reject malformed transcript structure before evaluating receipt metadata:
    # a matching final-answer hash alone does not establish four ordered turns.
    if (type(expected_sequence) is not int
            or expected_sequence not in ((1,) if _prefix_only is True else (2, 3))
            or (expected_sequence in (1, 3) and require_full_transcript_pin is not True)
            or not isinstance(dialog_id, str) or not dialog_id.strip()
            or not isinstance(expected_messages, list)
            or len(expected_messages) != 2 * expected_sequence):
        return False
    if any(not isinstance(row, dict) or row.get('role') != role
           or not isinstance(row.get('content'), str)
           for row, role in zip(expected_messages,
                                ('user', 'assistant') * expected_sequence)):
        return False
    # A witness scoped to this dialog cannot legitimize a foreign session's
    # individual S03 rows, even when all four role/text values are identical.
    # Legacy messages without explicit dialog_id remain compatible.
    if (not distinct_explicit_message_ids(expected_messages)
            or any('dialog_id' in row and row['dialog_id'] != dialog_id
                   for row in expected_messages)):
        return False
    if require_full_transcript_pin:
        # A partial row-level dialog scope is not a coherent four-turn S03
        # provenance witness. Preserve wholly legacy unscoped histories.
        row_dialog_presence = ['dialog_id' in row for row in expected_messages]
        if any(row_dialog_presence) and not all(row_dialog_presence):
            return False
    transcript_sha = multiturn_transcript_sha256(
        expected_messages, expected_sequence=expected_sequence, _prefix_only=_prefix_only)
    if transcript_sha is None:
        return False
    # Text/digest equality alone cannot establish four distinct persisted S03
    # records. Strict B5 acceptance requires independently readable row IDs.
    # The legacy A1 source helper and browser-history compatibility stay intact.
    if require_full_transcript_pin:
        row_ids = [row.get('message_id') for row in expected_messages]
        if (any(not isinstance(value, str) or not value.strip()
                or value != value.strip() or not value.isprintable()
                for value in row_ids)
                or len({value.strip() for value in row_ids}) != len(expected_messages)):
            return False
    if require_full_transcript_pin and any(
            'session_id' in row for row in expected_messages):
        # A four-row RU/ES S03 readback cannot mix authenticated sessions.
        # Historical rows may omit session_id entirely. If any row supplies
        # this metadata, every row must provide the same nonblank exact ID;
        # a partial annotation must not certify cross-session continuity.
        # This alone is NOT an owner-cookie or independent writer proof.
        session_ids = [row.get('session_id') for row in expected_messages]
        if (any(not isinstance(value, str) or not value.strip()
                or value != value.strip() or not value.isprintable()
                for value in session_ids)
                or len(set(session_ids)) != 1):
            return False
    if (not isinstance(writer_receipt, dict) or not isinstance(independent_readback, dict)
            or writer_receipt is independent_readback):
        return False
    if require_full_transcript_pin:
        # Session-consistent rows alone do not bind a trusted S03 writer
        # event to the independent reader's owner session. If any witness
        # exposes a session pin, ALL three witnesses must agree exactly.
        # Entirely unannotated older rows/receipts remain compatible.
        row_scoped = 'session_id' in expected_messages[0]
        witness_scoped = ('session_id' in writer_receipt
                          or 'session_id' in independent_readback)
        if row_scoped or witness_scoped:
            if not row_scoped:
                return False
            session_id = expected_messages[0]['session_id']
            if (writer_receipt.get('session_id') != session_id
                    or independent_readback.get('session_id') != session_id):
                return False
    if require_full_transcript_pin:
        # The role/content fingerprint omits durable row identities. A stale
        # writer receipt can otherwise match newly replaced rows with the same
        # text. Both trusted witnesses must pin the same ordered four IDs.
        identity_sha = digest(json.dumps(
            row_ids, ensure_ascii=False, separators=(',', ':'),
            allow_nan=False).encode('utf-8'))
        if (writer_receipt.get('message_ids_sha256') != identity_sha
                or independent_readback.get('message_ids_sha256') != identity_sha):
            return False
    # A legacy writer/readback with only the last-answer SHA can match a
    # stale event even when the earlier RU/ES turns changed. In two-turn mode
    # BOTH independent witnesses must pin the complete four-message history.
    writer_history_sha = writer_receipt.get('full_transcript_sha256')
    readback_history_sha = independent_readback.get('full_transcript_sha256')
    if (require_full_transcript_pin
            or 'full_transcript_sha256' in writer_receipt
            or 'full_transcript_sha256' in independent_readback):
        if writer_history_sha != transcript_sha or readback_history_sha != transcript_sha:
            return False
    event_id = writer_receipt.get('event_id')
    turn_id = writer_receipt.get('turn_id')
    sequence = writer_receipt.get('sequence')
    if require_full_transcript_pin and any(
            not isinstance(value, str) or value != value.strip()
            or not value.isprintable()
            for value in (event_id, turn_id)):
        # Strict RU/ES S03 witnesses must not treat padded or invisible
        # event/turn aliases as durable identities. The legacy source-only
        # A1 validation contract remains unchanged.
        return False
    if (writer_receipt.get('source') != 'canonical_s03'
            or writer_receipt.get('verified') is not True
            or writer_receipt.get('durable') is not True
            or not isinstance(event_id, str) or not event_id.strip()
            or not isinstance(turn_id, str) or not turn_id.strip()
            or type(sequence) is not int or sequence != expected_sequence
            or writer_receipt.get('dialog_id') != dialog_id):
        return False
    if (independent_readback.get('source') != 'canonical_s03'
            or independent_readback.get('independent') is not True
            or independent_readback.get('event_id') != event_id
            or independent_readback.get('turn_id') != turn_id
            or type(independent_readback.get('sequence')) is not int
            or independent_readback['sequence'] != sequence
            or independent_readback.get('dialog_id') != dialog_id
            or independent_readback.get('messages') != expected_messages):
        return False
    answer = expected_messages[-1].get('content') if expected_messages else None
    expected_hash = (digest(answer.encode('utf-8'))
                     if isinstance(answer, str) and answer.strip() else None)
    if not expected_hash or independent_readback.get('full_answer_sha256') != expected_hash:
        return False
    # An optional writer-side final-answer hash must corroborate the same
    # fourth message. A contradictory writer must not be certified just
    # because independent history/readback happened to match the browser.
    # Older writer receipts without this field remain source-compatible;
    # they never replace the required trusted native writer/readback proof.
    return ('full_answer_sha256' not in writer_receipt
            or writer_receipt['full_answer_sha256'] == expected_hash)


def strict_owner_json_bytes(raw, limit=200000):
    """Decode bounded UTF-8 JSON without ambiguous wire representations."""
    if len(raw)>limit:
        raise RuntimeError('HOLD_OWNER_HTTP_SIZE')
    # The owner history is an RFC 8259 UTF-8 wire witness. json.loads(bytes)
    # auto-detects UTF-16/32; a second browser or canonical S03 reader may
    # decode the same bytes differently. Reject ambiguous encodings before
    # checking four persisted RU/ES turns, without changing response limits.
    if b'\x00' in raw:
        raise RuntimeError('HOLD_OWNER_HTTP_UTF8_WIRE')
    try:
        decoded = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        raise RuntimeError('HOLD_OWNER_HTTP_UTF8_WIRE') from None
    if decoded.startswith('\ufeff'):
        raise RuntimeError('HOLD_OWNER_HTTP_UTF8_WIRE')
    # Bounded GET bodies can still contain enough nested containers to
    # exhaust Python's JSON decoder stack, concealing a malformed owner-
    # history witness behind an unclassified RecursionError. Preflight the
    # structure without counting brackets inside quoted/escaped RU/ES text.
    # This is a wire-evidence guard, NOT a model context/token limit.
    depth = 0
    in_string = False
    escaped = False
    for char in decoded:
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in '[{':
            depth += 1
            if depth > 64:
                raise RuntimeError('HOLD_OWNER_HTTP_JSON_DEPTH')
        elif char in ']}':
            depth -= 1
    # Browser history and S03 candidate witnesses must not accept ambiguous
    # JSON objects: json.loads normally keeps the last duplicate key, allowing
    # conflicting dialog/message identities to be silently overwritten.
    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError('HOLD_OWNER_HTTP_DUPLICATE_JSON_KEY')
            value[key] = item
        return value

    def finite_float(literal):
        value = float(literal)
        if not math.isfinite(value):
            raise RuntimeError('HOLD_OWNER_HTTP_NONFINITE_JSON_NUMBER')
        return value

    def reject_nonfinite(_literal):
        raise RuntimeError('HOLD_OWNER_HTTP_NONFINITE_JSON_NUMBER')

    def bounded_int(literal):
        # A legal-size history GET can still include a 4301+ digit JSON
        # integer. Python 3.11 rejects it with an unclassified ValueError;
        # bound it first, preserving ordinary integer metadata and all text.
        if len(literal.lstrip('-')) > 1024:
            raise RuntimeError('HOLD_OWNER_HTTP_INTEGER_DIGITS')
        try:
            return int(literal)
        except ValueError:
            raise RuntimeError('HOLD_OWNER_HTTP_INTEGER_DIGITS') from None

    # All callers consume one owner-scoped API object. A syntactically valid
    # JSON scalar/list/null or a truncated document is not trusted history,
    # even if it passed wire/MIME checks. Classify shape failures as HOLD
    # instead of leaking JSONDecodeError or later unclassified .get() errors.
    try:
        document = json.loads(decoded, object_pairs_hook=unique_keys,
                              parse_constant=reject_nonfinite, parse_float=finite_float,
                              parse_int=bounded_int)
    except json.JSONDecodeError:
        raise RuntimeError('HOLD_OWNER_HTTP_JSON_ROOT') from None
    return document


def canonical_s03_pinned_evidence_valid(writer_raw, readback_raw,
                                        writer_sha256, readback_sha256,
                                        dialog_id, expected_messages, *,
                                        expected_session_id, expected_sequence=2,
                                        expected_prior_messages=None,
                                        prior_witnesses=None, _prefix_only=False):
    """Verify immutable bytes for the strict two-/three-turn S03 contract.

    The caller MUST obtain both expected hashes independently from the
    authorized owner/immutable-verifier path, not from the candidate files.
    The expected session ID must also come from authenticated owner context,
    independently of the candidate receipts and transcript. The dialog ID
    must be canonical and explicitly present on every persisted row.
    For turn three the caller must independently obtain the prior four
    authenticated rows and independently pinned sequence-two writer/readback
    bytes before the next request, not from either new witness. The prior
    tuple is (writer bytes, reader bytes, writer SHA256, reader SHA256).
    This pure adapter cannot establish that authority or native admission.
    It never reads S03, accepts a browser history as a writer, or issues POST.
    """
    if (type(expected_sequence) is not int
            or expected_sequence not in ((1,) if _prefix_only is True else (2, 3))
            or not isinstance(dialog_id, str) or not dialog_id.strip()
            or dialog_id != dialog_id.strip() or not dialog_id.isprintable()
            or not isinstance(expected_session_id, str)
            or not expected_session_id.strip()
            or expected_session_id != expected_session_id.strip()
            or not expected_session_id.isprintable()
            or not isinstance(expected_messages, list)
            or len(expected_messages) != 2 * expected_sequence
            or any(not isinstance(row, dict) or
                   row.get('session_id') != expected_session_id or
                   row.get('dialog_id') != dialog_id
                   for row in expected_messages)
            or type(writer_raw) is not bytes or type(readback_raw) is not bytes
            or not 0 < len(writer_raw) <= 200000
            or not 0 < len(readback_raw) <= 200000
            or any(not isinstance(pin, str) or
                   re.fullmatch(r'[a-f0-9]{64}', pin) is None
                   for pin in (writer_sha256, readback_sha256))
            or writer_sha256 == readback_sha256
            or digest(writer_raw) != writer_sha256
            or digest(readback_raw) != readback_sha256):
        return False
    if expected_sequence == 3:
        if (not isinstance(expected_prior_messages, list)
                or len(expected_prior_messages) != 4
                or expected_messages[:4] != expected_prior_messages):
            return False
        if (type(prior_witnesses) is not tuple or len(prior_witnesses) != 4
                or not canonical_s03_pinned_evidence_valid(
                    *prior_witnesses, dialog_id, expected_prior_messages,
                    expected_session_id=expected_session_id)):
            return False
    elif expected_prior_messages is not None or prior_witnesses is not None:
        return False
    try:
        writer = strict_owner_json_bytes(writer_raw)
        readback = strict_owner_json_bytes(readback_raw)
        if (not isinstance(writer, dict) or not isinstance(readback, dict)
                or writer.get('session_id') != expected_session_id
                or readback.get('session_id') != expected_session_id):
            return False
        if expected_sequence == 3:
            prior_writer = strict_owner_json_bytes(prior_witnesses[0])
            # A third turn must have its own durable event and turn identity,
            # not merely updated text and sequence under a reused receipt ID.
            if any(writer.get(key) == prior_writer.get(key)
                   for key in ('event_id', 'turn_id')):
                return False
        return canonical_s03_proof_valid(
            writer, readback, dialog_id, expected_messages,
            require_full_transcript_pin=True, expected_sequence=expected_sequence,
            _prefix_only=_prefix_only)
    except (RuntimeError, ValueError, TypeError, UnicodeError, RecursionError):
        return False


def canonical_s03_firstturn_prefix_valid(writer_raw, readback_raw, writer_sha256,
                                         readback_sha256, dialog_id, prior_messages, *,
                                         expected_session_id):
    """Read-only gate for an EXISTING first turn; not multi-turn acceptance.

    Pins and owner/session/dialog selection must come from the independent
    trusted verifier before any second POST. Never recreate/replay turn one.
    This function does not grant native admission or perform network I/O.
    """
    return canonical_s03_pinned_evidence_valid(
        writer_raw, readback_raw, writer_sha256, readback_sha256, dialog_id,
        prior_messages, expected_session_id=expected_session_id,
        expected_sequence=1, _prefix_only=True)


def canonical_s03_resumed_second_turn_valid(writer_raw, readback_raw, writer_sha256,
                                            readback_sha256, dialog_id, messages, *,
                                            expected_session_id, prior_messages,
                                            prior_witnesses):
    """Bind subsequent turn-two evidence to the independently pinned old turn.

    The caller must obtain prior_messages and prior_witnesses before the
    second POST; these are not derived from the new receipt. Keep the old
    two exact rows and require two new durable IDs plus a fresh event/turn.
    """
    if (not isinstance(prior_messages, list) or len(prior_messages) != 2
            or not isinstance(messages, list) or len(messages) != 4
            or messages[:2] != prior_messages
            or type(prior_witnesses) is not tuple or len(prior_witnesses) != 4
            or not canonical_s03_firstturn_prefix_valid(
                *prior_witnesses, dialog_id, prior_messages,
                expected_session_id=expected_session_id)
            or not canonical_s03_pinned_evidence_valid(
                writer_raw, readback_raw, writer_sha256, readback_sha256,
                dialog_id, messages, expected_session_id=expected_session_id)):
        return False
    try:
        old = strict_owner_json_bytes(prior_witnesses[0])
        new = strict_owner_json_bytes(writer_raw)
        return all(new.get(key) != old.get(key) for key in ('event_id', 'turn_id'))
    except (RuntimeError, ValueError, TypeError, UnicodeError, RecursionError):
        return False

DIALOG = "synthetic-owner-dialog"
RU = "Запомни последовательность 🪐"
FIRST = "1,2,3,4,5,6,7,8,9,10"
LAST = "10,9,8,7,6,5,4,3,2,1"

def rows(spanish_prompt):
    return [dict(role="user", content=RU), dict(role="assistant", content=FIRST),
            dict(role="user", content=spanish_prompt), dict(role="assistant", content=LAST)]

class PortTests(unittest.TestCase):
    def test_pinned_s03_third_turn_requires_independent_prior_prefix(self):
        prior = [dict(row, message_id=f"row-{i}", session_id="owner-session",
                      dialog_id=DIALOG)
                 for i, row in enumerate(rows("Sigue en español 🪐"), 1)]
        current = [dict(row) for row in prior] + [
            dict(role="user", content="¿Y ahora qué recuerdas? 🪐",
                 message_id="row-5", session_id="owner-session", dialog_id=DIALOG),
            dict(role="assistant", content="Помню весь диалог. Sí.",
                 message_id="row-6", session_id="owner-session", dialog_id=DIALOG)]
        def wire(obj):
            return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        def pin(raw):
            return hashlib.sha256(raw).hexdigest()
        def witnesses(history, sequence=3, event=None, turn=None):
            full = pin(json.dumps(
                [{"role": x["role"], "content": x["content"]} for x in history],
                ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
            ids = pin(wire([x["message_id"] for x in history]))
            common = dict(source="canonical_s03", event_id=event or f"evt-{sequence:02}",
                          turn_id=turn or f"turn-{sequence:02}", sequence=sequence, dialog_id=DIALOG,
                          session_id="owner-session", full_transcript_sha256=full,
                          message_ids_sha256=ids)
            return (wire(dict(common, verified=True, durable=True)),
                    wire(dict(common, independent=True, messages=history,
                              full_answer_sha256=pin(history[-1]["content"].encode()))))
        pw, pr = witnesses(prior, 2)
        prior_pins = (pw, pr, pin(pw), pin(pr))
        def check(history=current, old=prior, sequence=3, receipt_sequence=3,
                  previous=prior_pins, event=None, turn=None):
            w, r = witnesses(history, receipt_sequence, event, turn)
            return canonical_s03_pinned_evidence_valid(
                w, r, pin(w), pin(r), DIALOG, history,
                expected_session_id="owner-session", expected_sequence=sequence,
                expected_prior_messages=old, prior_witnesses=previous)
        self.assertTrue(check())
        self.assertFalse(check(previous=None))
        self.assertFalse(check(previous=(pw, pr, pin(pr), pin(pw))))
        self.assertFalse(check(previous=(pw, pr, pin(pw), "0" * 64)))
        self.assertFalse(check(event="evt-02"))
        self.assertFalse(check(turn="turn-02"))
        wrong_prior = [dict(row) for row in prior]
        wrong_prior[1]["content"] = "Different previous answer"
        ww, wr = witnesses(wrong_prior, 2)
        self.assertFalse(check(previous=(ww, wr, pin(ww), pin(wr))))
        self.assertFalse(check(old=None))
        self.assertFalse(check(old=prior[:2]))
        self.assertFalse(check(history=current[2:]))
        self.assertFalse(check(sequence=2))
        self.assertFalse(check(sequence=True))
        self.assertFalse(check(receipt_sequence=2))
        replaced = [dict(x) for x in current]
        replaced[1]["content"] = "Rewritten prior answer"
        self.assertFalse(check(history=replaced))
        replaced = [dict(x) for x in current]
        replaced[0]["message_id"] = "replacement-row"
        self.assertFalse(check(history=replaced))
        duplicate = [dict(x) for x in current]
        duplicate[-1]["message_id"] = prior[0]["message_id"]
        self.assertFalse(check(history=duplicate))
        foreign = [dict(x) for x in current]
        foreign[-1]["dialog_id"] = "foreign-dialog"
        self.assertFalse(check(history=foreign))
        self.assertIsNone(multiturn_transcript_sha256(current))
        self.assertIsNotNone(multiturn_transcript_sha256(current, expected_sequence=3))

    def test_existing_first_turn_prefix_resume_without_replay(self):
        current = [dict(row, message_id=f"row-{i}", session_id="owner-session",
                        dialog_id=DIALOG)
                   for i, row in enumerate(rows("¿Qué recuerdas? 🪐"), 1)]
        prior = [dict(row) for row in current[:2]]
        def wire(obj):
            return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        def pin(raw):
            return hashlib.sha256(raw).hexdigest()
        def witnesses(history, sequence, event=None, turn=None):
            full = pin(json.dumps(
                [{"role": x["role"], "content": x["content"]} for x in history],
                ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
            common = dict(source="canonical_s03", event_id=event or f"evt-{sequence}",
                          turn_id=turn or f"turn-{sequence}", sequence=sequence,
                          dialog_id=DIALOG, session_id="owner-session",
                          full_transcript_sha256=full,
                          message_ids_sha256=pin(wire([x["message_id"] for x in history])))
            w = wire(dict(common, verified=True, durable=True))
            r = wire(dict(common, independent=True, messages=history,
                          full_answer_sha256=pin(history[-1]["content"].encode())))
            return w, r, pin(w), pin(r)
        previous = witnesses(prior, 1)
        self.assertTrue(canonical_s03_firstturn_prefix_valid(
            *previous, DIALOG, prior, expected_session_id="owner-session"))
        self.assertFalse(canonical_s03_pinned_evidence_valid(
            *previous, DIALOG, prior, expected_session_id="owner-session",
            expected_sequence=1))
        self.assertIsNone(multiturn_transcript_sha256(prior, expected_sequence=1))
        def check(history=current, prefix=prior, pins=previous, event=None, turn=None):
            return canonical_s03_resumed_second_turn_valid(
                *witnesses(history, 2, event, turn), DIALOG, history,
                expected_session_id="owner-session", prior_messages=prefix,
                prior_witnesses=pins)
        self.assertTrue(check())
        self.assertFalse(check(pins=None))
        self.assertFalse(check(pins=(*previous[:2], "0"*64, previous[3])))
        self.assertFalse(check(event="evt-1"))
        self.assertFalse(check(turn="turn-1"))
        rewritten = [dict(row) for row in current]
        rewritten[1]["content"] = "Подмена предыдущего ответа"
        self.assertFalse(check(history=rewritten))
        duplicated = [dict(row) for row in current]
        duplicated[-1]["message_id"] = prior[0]["message_id"]
        self.assertFalse(check(history=duplicated))
        self.assertFalse(canonical_s03_firstturn_prefix_valid(
            *previous, DIALOG, prior, expected_session_id="different-owner"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
