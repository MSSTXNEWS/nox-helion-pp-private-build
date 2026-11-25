import contextlib
import tempfile
import unittest
from pair_projection import compare_pair
from link_fields import derive_link_fields
from canonical_text import recover_text
from projection_match import compare_projection
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, raw, sha

class PairProjection(unittest.TestCase):
    def test_real_modules_single_chain(self):
        with contextlib.ExitStack() as stack:
            def retained(rewrite=False):
                result = []
                for n in (1, 2, 3):
                    _, (w, r, ws, rs) = checkpoint(n, rewrite=rewrite)
                    fds = []
                    for data in (w, r):
                        f = stack.enter_context(tempfile.TemporaryFile())
                        f.write(data); f.flush(); fds.append(f.fileno())
                    result.append((*fds, ws, rs))
                return tuple(result)
            producer, verifier, divergent = retained(), retained(), retained(True)
            scope = dict(dialog_id=DIALOG, session_id=SESSION)
            def make(n, chain, **changes):
                terminal = dict(status="STREAM_ENDED_READBACK_REQUIRED", sequence=n,
                    conversation_id="conversation", exchange_id=f"ex-{n}",
                    physical_dialog_id="physical", request_id=f"req-{n}", attempt_id=f"attempt-{n}")
                build = changes.pop("served_sha256", sha(b"build"))
                terminal.update(changes)
                fields = derive_link_fields(**scope, sequence=n, artifacts=chain[:n])
                link = raw(dict(terminal, **fields, schema="NOX_B3_S03_TERMINAL_LINK_V1",
                                served_sha256=build))
                turn = dict(terminal=terminal, served_sha256=build, link_bytes=link, link_sha256=sha(link))
                candidate = recover_text(**scope, sequence=n, artifacts=chain[:n], **turn)
                self.assertEqual(compare_projection(candidate, **scope, sequence=n,
                    artifacts=chain[:n], **turn)["status"], "S03_PROJECTION_MATCHED_OFFLINE")
                return candidate, turn
            c2, t2 = make(2, producer)
            c3, t3 = make(3, producer)
            def verify(candidates, turns):
                return compare_pair(candidates, **scope, artifacts=verifier, turns=turns)
            out = verify((c2, c3), (t2, t3))
            self.assertEqual(out["status"], "S03_PROJECTION_PAIR_MATCHED_OFFLINE")
            self.assertEqual(tuple(x["sequence"] for x in out["turns"]), (2, 3))
            for key in ("authentication_verified", "native_accepted", "ack_allowed", "next_post_allowed"):
                self.assertIs(out[key], False)
            # Every altered turn is individually valid against its own evidence.
            alternatives = [make(3, divergent), make(3, producer, conversation_id="other"),
                make(3, producer, physical_dialog_id="other"), make(3, producer, served_sha256=sha(b"other")),
                make(3, producer, exchange_id="ex-2"), make(3, producer, request_id="req-2"),
                make(3, producer, attempt_id="attempt-2")]
            for candidate, turn in alternatives:
                with self.assertRaises(ValueError):
                    verify((c2, candidate), (t2, turn))
            with self.assertRaises(ValueError):
                verify((c3, c2), (t3, t2))
            with self.assertRaises(ValueError):
                verify((c2, dict(c3, assistant_text="truncated")), (t2, t3))
if __name__ == "__main__":
    unittest.main(verbosity=2)
