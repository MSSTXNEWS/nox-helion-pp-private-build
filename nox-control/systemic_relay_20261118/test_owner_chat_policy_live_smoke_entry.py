"""Byte-identical embedded child script; the test never executes its native wrapper."""
import ast
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
ENTRY=HERE/"owner_chat_policy_live_smoke_entry.py"
SOURCE=HERE/"owner_chat_policy_live_smoke.py"


class LiveSmokeEntryTests(unittest.TestCase):
    def test_pinned_inline_venv_script_exact_bytes(self):
        script=ENTRY.read_text("utf-8")
        tree=ast.parse(script)
        binding=[n for n in tree.body if isinstance(n,ast.Assign)
                 and any(isinstance(x,ast.Name) and x.id=="SOURCE" for x in n.targets)]
        self.assertEqual(len(binding),1)
        embedded=ast.literal_eval(binding[0].value)
        self.assertEqual(embedded,SOURCE.read_text("utf-8"))
        self.assertTrue(embedded.startswith("#!/usr/bin/env python3\n"))
        self.assertIn('"/root/nox/venv/bin/python"',script)
        self.assertIn('capture_output=True',script)
        self.assertIn('PYTHONDONTWRITEBYTECODE="1"',script)
        self.assertIn('if line.startswith("NOX_MAINT_")',script)


if __name__=="__main__":
    unittest.main()
