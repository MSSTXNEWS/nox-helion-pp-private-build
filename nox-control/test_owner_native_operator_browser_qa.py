"""Exact bundle tests for the pinned one-stream owner browser action."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import owner_native_operator as operator


class BrowserActionScopeTests(unittest.TestCase):
    def test_browser_action_selects_only_the_single_stream_bundle(self):
        self.assertEqual(
            operator.FILES["browser_qa"],
            "nox-control/owner_browser_stream_only_entry.py",
        )
        names = (
            "owner_chat_browser_qa.py",
            "owner_chat_browser_transport_qa.py",
            "owner_chat_browser_release_qa.py",
            "owner_chat_stream_only_qa.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                Path("nox-control").mkdir()
                paths = []
                for name in names:
                    path = Path("nox-control") / name
                    path.write_text("fixture", encoding="utf-8")
                    paths.append(str(path))
                selected = operator.repair_bundle_paths(
                    "browser_qa", operator.FILES["browser_qa"], tuple(paths)
                )
                self.assertEqual(selected, tuple(paths))
            finally:
                os.chdir(previous)

    def test_repair_and_other_actions_do_not_alias_browser_qa(self):
        self.assertNotEqual(operator.FILES["repair"], operator.FILES["browser_qa"])
        self.assertIn("browser_qa", operator.FILES)
        self.assertEqual(
            operator.SCOPED_REPAIR_BUNDLES[
                "nox-control/owner_browser_stream_only_entry.py"
            ],
            (
                "owner_chat_browser_qa.py",
                "owner_chat_browser_transport_qa.py",
                "owner_chat_browser_release_qa.py",
                "owner_chat_stream_only_qa.py",
            ),
        )


if __name__ == "__main__":
    unittest.main()
