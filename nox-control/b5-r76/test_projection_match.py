import contextlib
import tempfile
import unittest
from projection_match import compare_projection
from canonical_text import recover_text
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, raw, sha

class Match(unittest.TestCase):
    def test_independent_projection(self):
        with contextlib.ExitStack() as stack:
            def retain():
                artifacts=[]
                for n in (1,2,3):
                    _, (w,r,ws,rs)=checkpoint(n)
                    fds=[]
                    for data in (w,r):
                        f=stack.enter_context(tempfile.TemporaryFile())
                        f.write(data); f.flush(); fds.append(f.fileno())
                    artifacts.append((*fds,ws,rs))
                return artifacts
            producer, verifier = retain(), retain()
            for n in (2,3):
                terminal=dict(status="STREAM_ENDED_READBACK_REQUIRED",sequence=n,
                    conversation_id="conversation",exchange_id=f"ex-{n}",
                    physical_dialog_id="physical",request_id=f"req-{n}",attempt_id=f"attempt-{n}")
                build=sha(b"served browser")
                ws,rs=verifier[n-1][2:]
                link=raw(dict(terminal,schema="NOX_B3_S03_TERMINAL_LINK_V1",
                    served_sha256=build,s03_dialog_id=DIALOG,s03_session_id=SESSION,
                    s03_event_id=f"event-{n}",s03_turn_id=f"turn-{n}",
                    user_message_id=f"message-{2*n-2}",assistant_message_id=f"message-{2*n-1}",
                    writer_sha256=ws,readback_sha256=rs))
                args=dict(dialog_id=DIALOG,session_id=SESSION,sequence=n,
                    terminal=terminal,served_sha256=build,link_bytes=link,link_sha256=sha(link))
                proof=recover_text(**args,artifacts=tuple(producer[:n]))
                independent=dict(args,artifacts=tuple(verifier[:n]))
                self.assertNotEqual(producer[n-1][:2],verifier[n-1][:2])
                match=compare_projection(proof,**independent)
                self.assertEqual(match["status"],"S03_PROJECTION_MATCHED_OFFLINE")
                self.assertIs(match["ack_allowed"],False)
                self.assertIs(match["authentication_verified"],False)
                for k,v in proof.items():
                    bad=0 if type(v) is bool else (True if type(v) is int else v+"x")
                    with self.subTest(n=n,key=k), self.assertRaises(ValueError):
                        compare_projection(dict(proof,**{k:bad}),**independent)
                for bad in (dict(proof,extra=True),{k:v for k,v in proof.items() if k!="link_sha256"}):
                    with self.assertRaises(ValueError):
                        compare_projection(bad,**independent)
                with self.assertRaises(ValueError):
                    compare_projection(proof,**dict(independent,link_sha256=sha(b"wrong")))
if __name__=="__main__":
    unittest.main(verbosity=2)
