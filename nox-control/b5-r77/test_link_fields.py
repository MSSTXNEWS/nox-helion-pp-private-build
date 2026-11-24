import contextlib
import tempfile
import unittest
from link_fields import derive_link_fields
from canonical_text import recover_text
from projection_match import compare_projection
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, raw, sha, TEXT

class LinkFields(unittest.TestCase):
    def test_retained_s03_link_roundtrip(self):
        with contextlib.ExitStack() as stack:
            def retain(rewrite=False):
                out = []
                for n in (1, 2, 3):
                    _, (w, r, ws, rs) = checkpoint(n, rewrite=rewrite and n == 3)
                    fds = []
                    for data in (w, r):
                        f = stack.enter_context(tempfile.TemporaryFile())
                        f.write(data); f.flush(); fds.append(f.fileno())
                    out.append((*fds, ws, rs))
                return tuple(out)
            producer, verifier, broken = retain(), retain(), retain(True)
            for n in (2, 3):
                scope = dict(dialog_id=DIALOG, session_id=SESSION, sequence=n)
                fields = derive_link_fields(**scope, artifacts=producer[:n])
                self.assertEqual(set(fields), {
                    "s03_dialog_id", "s03_session_id", "s03_event_id",
                    "s03_turn_id", "user_message_id", "assistant_message_id",
                    "writer_sha256", "readback_sha256"})
                self.assertEqual(fields["assistant_message_id"], f"message-{2*n-1}")
                self.assertEqual(fields["s03_event_id"], f"event-{n}")
                # Synthetic owner supplies physical terminal/build independently.
                terminal = dict(status="STREAM_ENDED_READBACK_REQUIRED", sequence=n,
                    conversation_id="conversation", exchange_id=f"ex-{n}",
                    physical_dialog_id="physical", request_id=f"req-{n}", attempt_id=f"attempt-{n}")
                build = sha(b"served browser")
                link = raw(dict(terminal, **fields, schema="NOX_B3_S03_TERMINAL_LINK_V1",
                                served_sha256=build))
                args = dict(scope, terminal=terminal, served_sha256=build,
                            link_bytes=link, link_sha256=sha(link))
                proof = recover_text(**args, artifacts=producer[:n])
                self.assertEqual(proof["assistant_text"], TEXT[2*n-1])
                match = compare_projection(proof, **args, artifacts=verifier[:n])
                self.assertEqual(match["status"], "S03_PROJECTION_MATCHED_OFFLINE")
                self.assertIs(match["ack_allowed"], False)
                self.assertIs(match["native_accepted"], False)
                self.assertNotEqual(producer[n-1][:2], verifier[n-1][:2])
                with self.assertRaises(ValueError):
                    derive_link_fields(**dict(scope, session_id="other"), artifacts=producer[:n])
                with self.assertRaises(ValueError):
                    derive_link_fields(**scope, artifacts=producer[:n-1])
                bad = producer[:n-1] + ((*producer[n-1][:2], sha(b"wrong"), producer[n-1][3]),)
                with self.assertRaises(ValueError):
                    derive_link_fields(**scope, artifacts=bad)
            with self.assertRaises(ValueError):
                derive_link_fields(dialog_id=DIALOG, session_id=SESSION, sequence=3, artifacts=broken)
            with self.assertRaises(ValueError):
                derive_link_fields(dialog_id=DIALOG, session_id=SESSION, sequence=True, artifacts=producer)
if __name__ == "__main__":
    unittest.main(verbosity=2)
