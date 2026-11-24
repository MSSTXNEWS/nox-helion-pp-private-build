import hashlib
import json
import unittest

from b5_r55_pinned import canonical_s03_pinned_evidence_valid
from b5_chain_guard import verify_existing_chain

DIALOG = "a" * 32
SESSION = "fixture-owner"
TEXT = ("Помни имя проекта 🪐", "Запомнил: NOX", "¿Qué recuerdas?",
        "Recuerdo NOX", "А теперь по-русски", "Помню NOX — sí 🪐")


def raw(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def checkpoint(n, *, event=None, turn=None, rewrite=False):
    rows = [dict(role=("user", "assistant")[i % 2], content=text,
                 message_id=f"message-{i}", dialog_id=DIALOG, session_id=SESSION)
            for i, text in enumerate(TEXT[:2*n])]
    if rewrite:
        rows[0]["content"] = "Подмена / cambio"
    projected = [dict(role=r["role"], content=r["content"]) for r in rows]
    common = dict(source="canonical_s03", event_id=event or f"event-{n}",
                  turn_id=turn or f"turn-{n}", sequence=n, dialog_id=DIALOG,
                  session_id=SESSION,
                  full_transcript_sha256=sha(json.dumps(
                      projected, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()),
                  message_ids_sha256=sha(raw([r["message_id"] for r in rows])))
    w = raw(dict(common, verified=True, durable=True))
    r = raw(dict(common, independent=True, messages=rows,
                 full_answer_sha256=sha(rows[-1]["content"].encode())))
    return rows, (w, r, sha(w), sha(r))


class ChainGuardTests(unittest.TestCase):
    def guard(self, *chain):
        return verify_existing_chain(dialog_id=DIALOG, session_id=SESSION, chain=chain)

    def test_valid_prefix_and_terminal(self):
        first, second, third = [checkpoint(n) for n in (1, 2, 3)]
        self.assertTrue(self.guard(first, second))
        self.assertTrue(self.guard(first, second, third))

    def test_nonadjacent_event_or_turn_reuse(self):
        first, second = checkpoint(1), checkpoint(2)
        for change in (dict(event="event-1"), dict(turn="turn-1"),
                       dict(event="event-1", turn="turn-1")):
            with self.subTest(change=change):
                rows, pins = checkpoint(3, **change)
                # Reproduce the old adjacent-only verifier gap.
                self.assertTrue(canonical_s03_pinned_evidence_valid(
                    *pins, DIALOG, rows, expected_session_id=SESSION,
                    expected_sequence=3, expected_prior_messages=second[0],
                    prior_witnesses=second[1]))
                self.assertFalse(self.guard(first, second, (rows, pins)))

    def test_prior_chain_rewrite_and_wrong_pins(self):
        first, second, third = [checkpoint(n) for n in (1, 2, 3)]
        self.assertFalse(self.guard(first, checkpoint(2, rewrite=True), third))
        self.assertFalse(self.guard(checkpoint(1, rewrite=True), second, third))
        self.assertFalse(self.guard((first[0], (*first[1][:2], "0"*64, first[1][3])),
                                    second, third))
        self.assertFalse(self.guard(second, third))
        self.assertFalse(self.guard(first, second, checkpoint(3, event="event-2")))
        self.assertFalse(self.guard(first, second, checkpoint(3, turn="turn-2")))
        self.assertFalse(verify_existing_chain(dialog_id=DIALOG, session_id="other",
                                                chain=(first, second, third)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
