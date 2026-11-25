import contextlib
import tempfile
import unittest
from canonical_text import recover_text
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, TEXT, raw, sha

class Recovery(unittest.TestCase):
    def test_retained_exact_text_and_scope(self):
        with contextlib.ExitStack() as stack:
            artifacts=[]
            for n in (1, 2, 3):
                _, (w, r, ws, rs) = checkpoint(n)
                fds=[]
                for data in (w, r):
                    f=stack.enter_context(tempfile.TemporaryFile())
                    f.write(data); f.flush(); fds.append(f.fileno())
                artifacts.append((*fds, ws, rs))
            for n in (2, 3):
                terminal=dict(status="STREAM_ENDED_READBACK_REQUIRED", sequence=n,
                    conversation_id="conversation", exchange_id=f"ex-{n}",
                    physical_dialog_id="physical", request_id=f"req-{n}", attempt_id=f"attempt-{n}")
                build=sha(b"served browser")
                ws, rs=artifacts[n-1][2:]
                link=dict(terminal, schema="NOX_B3_S03_TERMINAL_LINK_V1",
                    served_sha256=build, s03_dialog_id=DIALOG, s03_session_id=SESSION,
                    s03_event_id=f"event-{n}", s03_turn_id=f"turn-{n}",
                    user_message_id=f"message-{2*n-2}", assistant_message_id=f"message-{2*n-1}",
                    writer_sha256=ws, readback_sha256=rs)
                args=dict(dialog_id=DIALOG, session_id=SESSION, sequence=n,
                    artifacts=tuple(artifacts[:n]), terminal=terminal, served_sha256=build)
                def run(l=link, **kw):
                    data=raw(l)
                    return recover_text(**(dict(args, link_bytes=data, link_sha256=sha(data)) | kw))
                got=run()
                self.assertEqual(got["assistant_text"], TEXT[2*n-1])
                self.assertEqual(got["answer_sha256"], sha(TEXT[2*n-1].encode()))
                for flag in ("authentication_verified", "native_accepted", "ack_allowed", "next_post_allowed"):
                    self.assertIs(got[flag], False)
                for key in ("exchange_id", "attempt_id", "served_sha256", "s03_event_id",
                            "s03_session_id", "assistant_message_id", "writer_sha256", "readback_sha256"):
                    with self.subTest(n=n,key=key):
                        with self.assertRaises(ValueError):
                            run(dict(link, **{key:"foreign"}))
                for change in (dict(link_sha256=sha(b"wrong")), dict(sequence=1),
                               dict(artifacts=tuple(artifacts[:n-1])),
                               dict(terminal=dict(terminal,status="COMPLETED"))):
                    with self.assertRaises(ValueError):
                        run(**change)
if __name__ == "__main__":
    unittest.main(verbosity=2)
