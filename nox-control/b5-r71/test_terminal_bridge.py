import contextlib
import json
import os
import subprocess
import tempfile
import unittest
from terminal_canonical import terminal_canonical
from test_b5_chain_guard import checkpoint, DIALOG, SESSION

class TerminalBridge(unittest.TestCase):
    def test_actual_python_node_terminal(self):
        for n in (2, 3):
            with self.subTest(turn=n), contextlib.ExitStack() as stack:
                artifacts = []
                for i in range(1, n+1):
                    _, (w,r,ws,rs) = checkpoint(i)
                    pair = []
                    for raw in (w,r):
                        f = stack.enter_context(tempfile.TemporaryFile())
                        f.write(raw); f.flush()
                        pair.append(f.fileno())
                    artifacts.append((*pair,ws,rs))
                args = dict(dialog_id=DIALOG, session_id=SESSION,
                            expected_turn=n, artifacts=tuple(artifacts))
                canonical = terminal_canonical(**args)
                self.assertEqual(canonical["rows"], checkpoint(n)[0])
                result = subprocess.run(["node", os.environ["B5_R71_NODE"]],
                    input=json.dumps(canonical, ensure_ascii=False), text=True,
                    capture_output=True, check=True)
                self.assertEqual(json.loads(result.stdout), [True,False,False,False])
                with self.assertRaises(ValueError):
                    terminal_canonical(**dict(args, artifacts=tuple(artifacts[:-1])))
                with self.assertRaises(ValueError):
                    terminal_canonical(**dict(args, session_id="foreign"))
                bad = list(artifacts)
                bad[0] = (*bad[0][:2], "0"*64, bad[0][3])
                with self.assertRaises(ValueError):
                    terminal_canonical(**dict(args, artifacts=tuple(bad)))
                with self.assertRaises(TypeError):
                    terminal_canonical(**args, canonical=canonical)
