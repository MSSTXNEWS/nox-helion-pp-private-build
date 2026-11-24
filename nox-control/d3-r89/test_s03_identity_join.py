import copy
import os
import tempfile
import unittest
from test_b5_chain_guard import checkpoint, raw, sha, DIALOG, SESSION
from s03_identity_join import verify_join

class IdentityJoin(unittest.TestCase):
    def test_actual_retained_chain_and_distinct_terminal_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            sets, bindings, docs = [], [], []
            scope = dict(conversation_id="logical-conversation", dialog_id=DIALOG,
                         session_id=SESSION, served_sha256="a"*64, server_sha256="b"*64,
                         owner_admission_receipt_sha256="c"*64)
            for n in (1, 2, 3):
                rows, (w, r, ws, rs) = checkpoint(n)
                fds = []
                for kind, data in (("writer", w), ("reader", r)):
                    path = os.path.join(tmp, f"{kind}-{n}")
                    with open(path, "wb") as f:
                        f.write(data)
                    fd = os.open(path, os.O_RDONLY)
                    self.addCleanup(os.close, fd)
                    fds.append(fd)
                sets.append((*fds, ws, rs))
                if n == 1:
                    continue
                binding = dict(turn=n, exchange_id=f"ex-{n}", request_id=f"req-{n}",
                    attempt_id=f"attempt-{n}", user_message_id=rows[-2]["message_id"],
                    assistant_message_id=rows[-1]["message_id"], event_id=f"event-{n}",
                    turn_id=f"turn-{n}", writer_sha256=ws, readback_sha256=rs)
                bindings.append(binding)
                docs.append(dict(scope, **binding, schema="nox.transport.terminal-readback.v1",
                    state="TERMINAL_SAVED", eof=True, prompt_sha256=sha(rows[-2]["content"].encode()),
                    answer_sha256=sha(rows[-1]["content"].encode())))
            owner = dict(scope, schema="nox.owner.s03-transport-join.v1", bindings=bindings)
            def check(o=owner, d=docs, **overrides):
                data = raw(o)
                args = dict(owner_raw=data, owner_pin=sha(data),
                            terminal_pairs=tuple((raw(x), sha(raw(x))) for x in d),
                            descriptor_sets=tuple(sets), expected_scope=scope)
                return verify_join(**dict(args, **overrides))
            result = check()
            self.assertEqual(result["status"], "SCOPE_MATCHED_OFFLINE")
            self.assertFalse(any(v for k,v in result.items() if k != "status"))
            for field, value in (("session_id","foreign"), ("attempt_id","foreign"),
                                 ("request_id","foreign"), ("exchange_id","foreign"),
                                 ("assistant_message_id","foreign"), ("answer_sha256","0"*64),
                                 ("eof",False), ("state","STREAM_ENDED_READBACK_REQUIRED")):
                altered = copy.deepcopy(docs)
                altered[0][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError,"HOLD_"):
                    check(d=altered)
            # Matching but false owner and terminal identities must still fail B5 readback.
            altered = copy.deepcopy(owner)
            terminals = copy.deepcopy(docs)
            altered["bindings"][1]["assistant_message_id"] = "foreign"
            terminals[1]["assistant_message_id"] = "foreign"
            with self.assertRaisesRegex(ValueError,"HOLD_R89_CANONICAL_IDENTITY"):
                check(o=altered,d=terminals)
            with self.assertRaisesRegex(ValueError,"HOLD_R89_PIN"):
                check(owner_pin="0"*64)
