"""One bounded regression for exact pinned full-byte source citation proof."""
from __future__ import annotations

import hashlib
import unittest
from owner_source_span_proof import SourceProofHold, verify_span

SOURCE = "Полный источник: факт A. Факт B — подтверждён."
CONTENT = SOURCE.encode("utf-8")
ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
REV = "rev_19"
PERSONA = "nox_persona_main"
PINS = {ID: {"kind": "drive", "revision": REV, "sha256": hashlib.sha256(CONTENT).hexdigest(),
             "size_bytes": len(CONTENT), "persona_ids": [PERSONA]}}
EXCERPT = "Факт B — подтверждён."
START = CONTENT.index(EXCERPT.encode("utf-8"))


class CitationBoundaryTests(unittest.TestCase):
    def test_full_byte_provenance_and_fail_closed_cases(self):
        kwargs = dict(trusted_pins=PINS, source_id=ID, source_bytes=CONTENT,
                      source_revision=REV, persona_id=PERSONA, start_byte=START,
                      end_byte=START + len(EXCERPT.encode("utf-8")),
                      excerpt=EXCERPT, query_evidence=True, historical_unverified=False)
        proof = verify_span(**kwargs)
        self.assertEqual(proof.source_bytes, len(CONTENT))
        self.assertEqual(proof.citation_url, f"https://drive.google.com/file/d/{ID}/view")
        self.assertEqual(proof.proof_scope, "EXACT_BYTE_SPAN_ONLY_NOT_SEMANTIC_SUPPORT")
        cases = (
            ({"source_bytes": CONTENT[:-1]}, "HOLD_SOURCE_FULL_BYTES_MISSING"),
            ({"source_bytes": b"x" * len(CONTENT)}, "HOLD_SOURCE_CONTENT_SHA_MISMATCH"),
            ({"source_revision": "rev_18"}, "HOLD_SOURCE_REVISION_CHANGED"),
            ({"persona_id": "other_persona"}, "DENY_SOURCE_PERSONA_SCOPE"),
            ({"query_evidence": False}, "HOLD_SOURCE_QUERY_EVIDENCE_UNVERIFIED"),
            ({"historical_unverified": True}, "HOLD_SOURCE_QUERY_EVIDENCE_UNVERIFIED"),
            ({"excerpt": "Факт A."}, "HOLD_SOURCE_EXCERPT_NOT_EXACT"),
            ({"start_byte": START + 1}, "HOLD_SOURCE_EXCERPT_NOT_EXACT"),
            ({"end_byte": len(CONTENT) + 1}, "HOLD_SOURCE_EXCERPT_NOT_EXACT"),
            ({"trusted_pins": {}}, "HOLD_SOURCE_PIN_MISSING_OR_SCHEMA"),
        )
        for changes, code in cases:
            with self.subTest(code=code, changes=changes):
                with self.assertRaisesRegex(SourceProofHold, f"^{code}$"):
                    verify_span(**(kwargs | changes))


if __name__ == "__main__":
    unittest.main()
