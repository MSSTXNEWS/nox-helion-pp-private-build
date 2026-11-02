"""R60 strict source-only owner receipt JSON regression; not native/E07 proof."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase, main, mock

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_owner_receipt_same_head_gate_r23.py"
spec = importlib.util.spec_from_file_location("nox_t06_owner_receipt_r60", SOURCE)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class StrictGitOwnerReceiptR60(TestCase):
    def test_existing_owner_receipts_fail_closed_on_ambiguous_json(self):
        with mock.patch.object(owner, "read_at") as read:
            read.return_value = b'{"parts":[{"path":"src/a.py"}],"valid":true}'
            self.assertEqual(owner.strict_git_json_at("frozen", "receipt")["valid"], True)
            malicious = (
                b'{"parts":[],"parts":[{"path":"src/a.py"}]}',
                b'{"parts":[{"path":"safe","path":"evil"}]}',
                b'{"count":NaN}',
                b'{"count":Infinity}',
                b'{"count":1e9999}',
                b'[{"path":"src/a.py"}]',
                b'null',
                b'{"parts":\xff}',
                b'{"x":1}' + b" " * 1048576,
            )
            for payload in malicious:
                with self.subTest(payload=payload[:48]):
                    read.return_value = payload
                    with self.assertRaises(ValueError):
                        owner.strict_git_json_at("frozen", "receipt")

    def test_both_receipt_and_host50_mapping_use_strict_loader(self):
        import inspect
        body = inspect.getsource(owner.audit)
        self.assertIn("strict_git_json_at(head,path)", body)
        self.assertIn('strict_git_json_at(head,"proposals/NOX-PACK01-50/owner-binding-map.json")', body)


if __name__ == "__main__":
    main()
