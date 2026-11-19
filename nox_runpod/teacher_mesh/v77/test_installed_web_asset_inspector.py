from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from nox_runpod.teacher_mesh.v77.installed_web_asset_inspector import Hold, inspect


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.proc = self.base / "proc"
        self.pid = self.proc / "356735"
        self.pid.mkdir(parents=True)
        self.root = self.base / "web"
        (self.root / "assets").mkdir(parents=True)
        self.asset = b"window.nox = true;\n"
        (self.root / "assets" / "chat.js").write_bytes(self.asset)
        self.manifest = json.dumps({"assets": ["assets/chat.js"]}, separators=(",", ":")).encode()
        (self.root / "asset-manifest.json").write_bytes(self.manifest)
        self.uid = os.getuid()
        # /proc/PID/stat fields 3..22; field 22 (starttime) is 987654.
        fields = ["S"] + [str(i) for i in range(4, 23)]
        fields[19] = "987654"
        (self.pid / "stat").write_text(f"356735 (nox-web) " + " ".join(fields))
        (self.pid / "status").write_text(f"Name:\tnox-web\nUid:\t{self.uid}\t{self.uid}\t{self.uid}\t{self.uid}\n")
        (self.pid / "cmdline").write_bytes(b"node\0server.js\0--static-root\0" + str(self.root).encode() + b"\0")
        os.symlink("/usr/bin/node", self.pid / "exe")
        self.receipt = self.base / "owner-receipt.json"
        self.now = 2_000_000_000
        self._write_receipt()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_receipt(self, **changes):
        doc = {
            "pid": 356735,
            "start_ticks": 987654,
            "uid": self.uid,
            "issued_at": self.now - 10,
            "owner_lease": "CLEAR",
            "stop": "CLEAR",
            "entrypoint": "/usr/bin/node",
            "static_root": str(self.root),
            "manifest_rel": "asset-manifest.json",
            "serve_origin": "http://127.0.0.1:18775",
            "route_prefix": "/nox-web-v29",
            "allowlist": ["assets/chat.js"],
        }
        doc.update(changes)
        self.receipt.write_text(json.dumps(doc))
        self.receipt.chmod(0o600)

    def fetch(self, origin, prefix, rel, limit):
        self.assertEqual(origin, "http://127.0.0.1:18775")
        self.assertEqual(prefix, "/nox-web-v29")
        self.assertEqual(rel, "assets/chat.js")
        self.assertGreaterEqual(limit, len(self.asset))
        return self.asset

    def run_inspect(self, fetcher=None):
        return inspect(str(self.proc), str(self.receipt), now=self.now, fetcher=fetcher or self.fetch)

    def test_reports_manifest_and_installed_served_sha(self):
        result = self.run_inspect()
        self.assertEqual(result["result"], "PASS_READ_ONLY")
        self.assertEqual(result["manifest_bytes"], len(self.manifest))
        self.assertEqual(result["manifest_sha256"], hashlib.sha256(self.manifest).hexdigest())
        self.assertEqual(result["assets"][0]["sha256"], hashlib.sha256(self.asset).hexdigest())
        self.assertEqual(result["assets"][0]["served_sha256"], result["assets"][0]["sha256"])

    def test_stale_pid_start_ticks_hold(self):
        (self.pid / "stat").write_text("356735 (nox-web) " + " ".join(["S"] + ["1"] * 18 + ["987655"]))
        with self.assertRaisesRegex(Hold, "start time"):
            self.run_inspect()

    def test_unclear_lease_and_stop_hold(self):
        self._write_receipt(owner_lease="HELD")
        with self.assertRaisesRegex(Hold, "lease or STOP"):
            self.run_inspect()
        self._write_receipt(stop="ACTIVE")
        with self.assertRaisesRegex(Hold, "lease or STOP"):
            self.run_inspect()

    def test_receipt_expiry_holds(self):
        self._write_receipt(issued_at=self.now - 301)
        with self.assertRaisesRegex(Hold, "stale"):
            self.run_inspect()

    def test_root_symlink_and_asset_traversal_hold(self):
        alias = self.base / "web-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self._write_receipt(static_root=str(alias))
        (self.pid / "cmdline").write_bytes(b"node\0server.js\0--static-root\0" + str(alias).encode() + b"\0")
        with self.assertRaisesRegex(Hold, "symlink"):
            self.run_inspect()
        self._write_receipt(manifest_rel="../outside.json")
        with self.assertRaises(Hold):
            self.run_inspect()

    def test_loopback_served_bytes_must_match_disk(self):
        with self.assertRaisesRegex(Hold, "hash differs"):
            self.run_inspect(lambda *_: b"different served bytes")

    def test_manifest_allowlist_must_match_owner_receipt(self):
        self._write_receipt(allowlist=["assets/other.js"])
        with self.assertRaisesRegex(Hold, "allowlists differ"):
            self.run_inspect()

    def test_manifest_must_be_js_or_css_allowlist(self):
        (self.root / "asset-manifest.json").write_text(json.dumps({"assets": ["index.html"]}))
        self._write_receipt(allowlist=["index.html"])
        with self.assertRaisesRegex(Hold, "only JavaScript and CSS"):
            self.run_inspect()

    def test_non_loopback_origin_holds_before_fetch(self):
        self._write_receipt(serve_origin="http://example.com")
        with self.assertRaisesRegex(Hold, "numeric loopback"):
            self.run_inspect()


if __name__ == "__main__":
    unittest.main()
