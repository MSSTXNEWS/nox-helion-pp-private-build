"""P04 stdlib RAG host-compat tests: local HTTP fixture; no downloads/models/GPU."""
from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "rag_python_compat.py"
spec = importlib.util.spec_from_file_location("p04_python_host_compat", SOURCE)
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)
OWNER_A = "S-1-5-21-1100"
OWNER_B = "S-1-5-21-2200"


class EmbedFixture(BaseHTTPRequestHandler):
    count = 0

    def do_POST(self):
        if self.path != "/api/embed":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        args = json.loads(self.rfile.read(length))
        if args.get("model") != "fixture-embed" or args.get("truncate") is not False:
            self.send_response(400)
            self.end_headers()
            return
        vectors = []
        for item in args["input"]:
            if "alpha" in item.lower():
                vectors.append([1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 1.0, 0.0])
        EmbedFixture.count += 1
        data = json.dumps({"embeddings": vectors}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        return


class PythonHostCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), EmbedFixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.index_path = Path(self.tmp.name) / "index.json"
        self.rag = rag.LocalRag(
            f"http://127.0.0.1:{self.server.server_port}/", "fixture-embed",
            self.index_path
        )

    def test_real_shape_local_embed_ingest_citations_and_restart(self):
        ingested = self.rag.ingest_text(OWNER_A, "c1", "source1", "example.md", "alpha first document")
        self.assertEqual(ingested["indexed_chunks"], 1)
        self.assertEqual(len(ingested["sha256"]), 64)
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["schema"], rag.INDEX_SCHEMA)
        self.assertEqual(raw["vectorDimensions"], 3)
        self.assertEqual(raw["sources"][0]["chunks"][0]["chunkIndex"], 0)
        found = self.rag.search(OWNER_A, "c1", "alpha")
        self.assertEqual(found[0]["source_id"], "source1")
        self.assertEqual(found[0]["title"], "example.md")
        self.assertEqual(self.rag.search(OWNER_B, "c1", "alpha"), [])
        restarted = rag.LocalRag(
            f"http://127.0.0.1:{self.server.server_port}/", "fixture-embed",
            self.index_path
        )
        context = restarted.context(OWNER_A, "c1", "alpha")
        self.assertIn("SHA256:", context["context"])
        self.assertEqual(context["sources"][0]["verified"], True)
        self.assertEqual(context["sources"][0]["source_id"], "source1")
        adapter = rag.p02_callback(restarted, lambda tenant, principal:
                                   OWNER_A if (tenant, principal) == ("t", "p") else OWNER_B)
        self.assertEqual(adapter("t", "p", "c1", "alpha"), context)
        self.assertEqual(adapter("t", "other", "c1", "alpha")["sources"], [])

    def test_upsert_delete_isolation_and_persistence(self):
        self.rag.ingest_text(OWNER_A, "c1", "source1", "example.txt", "alpha first")
        self.rag.ingest_text(OWNER_A, "c1", "source1", "example.txt", "beta second")
        self.rag.ingest_text(OWNER_B, "c1", "source2", "another.txt", "alpha other")
        self.assertEqual(len(self.rag.search(OWNER_A, "c1", "beta")), 1)
        self.assertNotIn("alpha first", self.rag.search(OWNER_A, "c1", "beta")[0]["text"])
        self.assertFalse(self.rag.delete_source(OWNER_A, "c1", "source2"))
        self.assertTrue(self.rag.delete_source(OWNER_A, "c1", "source1"))
        self.assertEqual(self.rag.search(OWNER_A, "c1", "beta"), [])
        self.assertEqual(self.rag.delete_conversation(OWNER_B, "c1"), 1)
        reread = rag.LocalRag(
            f"http://127.0.0.1:{self.server.server_port}/", "fixture-embed",
            self.index_path
        )
        self.assertEqual(reread.search(OWNER_B, "c1", "alpha"), [])

    def test_fail_closed_invalid_scope_url_index_and_provenance(self):
        with self.assertRaises(rag.RagHold):
            rag.LocalRag("http://example.com:11434", "fixture-embed", self.index_path)
        with self.assertRaises(rag.RagHold):
            self.rag.ingest_text("bad SID", "c1", "src", "example.txt", "alpha")
        with self.assertRaises(rag.RagHold):
            self.rag.ingest_text(OWNER_A, "c1", "src", "../evil.txt", "alpha")
        self.assertEqual(self.rag.search(OWNER_A, "empty", "alpha"), [])
        self.rag.ingest_text(OWNER_A, "c1", "source1", "example.md", "alpha test")
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        index["sources"][0]["chunks"][0]["text"] = "altered"
        self.index_path.write_text(json.dumps(index), encoding="utf-8")
        with self.assertRaisesRegex(rag.RagHold, "RAG_CHUNK_PROVENANCE_INVALID"):
            self.rag.search(OWNER_A, "c1", "alpha")

    def test_authorized_file_ingestion_is_idempotent_and_updatable(self):
        source_file = Path(self.tmp.name) / "note.md"
        source_file.write_bytes(b"\xef\xbb\xbfalpha file")
        first = self.rag.ingest_file(OWNER_A, "c1", source_file)
        self.assertEqual(first["indexed_chunks"], 1)
        self.assertFalse(first["unchanged"])
        self.assertEqual(first["sha256"], rag._sha(source_file.read_bytes()))
        prior_calls = EmbedFixture.count
        second = self.rag.ingest_file(OWNER_A, "c1", source_file)
        self.assertEqual(EmbedFixture.count, prior_calls)
        self.assertTrue(second["unchanged"])
        source_file.write_text("beta changed file", encoding="utf-8")
        updated = self.rag.ingest_file(OWNER_A, "c1", source_file)
        self.assertFalse(updated["unchanged"])
        self.assertEqual(updated["source_id"], first["source_id"])
        self.assertEqual(len(self.rag.search(OWNER_A, "c1", "beta")), 1)

    def test_bad_file_and_foreign_owner_cannot_read_or_import(self):
        source_file = Path(self.tmp.name) / "invalid.md"
        source_file.write_bytes(b"\xff\xfe\xff")
        with self.assertRaisesRegex(rag.RagHold, "RAG_FILE_NOT_UTF8"):
            self.rag.ingest_file(OWNER_A, "c1", source_file)
        with self.assertRaisesRegex(rag.RagHold, "RAG_AUTHENTICATED_OWNER_SID_REQUIRED"):
            self.rag.ingest_file("not-owner", "c1", source_file)
        original = Path(self.tmp.name) / "keep.md"
        original.write_text("alpha safe", encoding="utf-8")
        link = Path(self.tmp.name) / "link.md"
        try:
            link.symlink_to(original)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unsupported")
        with self.assertRaisesRegex(rag.RagHold, "RAG_FILE_SYMLINK_BLOCKED"):
            self.rag.ingest_file(OWNER_A, "c1", link)
        self.assertEqual(original.read_text(encoding="utf-8"), "alpha safe")

    def test_legacy_source_with_oversized_title_holds_in_p02_adapter(self):
        self.rag.ingest_text(OWNER_A, "c1", "safe-source", "example.md", "alpha content")
        old = json.loads(self.index_path.read_text(encoding="utf-8"))
        old["sources"][0]["fileName"] = "x" * 201 + ".md"
        self.index_path.write_text(json.dumps(old), encoding="utf-8")
        with self.assertRaisesRegex(rag.RagHold, "RAG_PROVENANCE_P02_INCOMPATIBLE"):
            self.rag.context(OWNER_A, "c1", "alpha")

    def test_source_identity_and_symlink_fail_closed(self):
        original = Path(self.tmp.name) / "untouched.txt"
        original.write_text("safe", encoding="utf-8")
        if self.index_path.exists():
            self.index_path.unlink()
        try:
            self.index_path.symlink_to(original)
        except (OSError, NotImplementedError):
            self.skipTest("symlink operation unavailable")
        with self.assertRaisesRegex(rag.RagHold, "RAG_INDEX_SYMLINK"):
            self.rag.ingest_text(OWNER_A, "c1", "source1", "example.txt", "alpha")
        self.assertEqual(original.read_text(encoding="utf-8"), "safe")


if __name__ == "__main__":
    unittest.main()
