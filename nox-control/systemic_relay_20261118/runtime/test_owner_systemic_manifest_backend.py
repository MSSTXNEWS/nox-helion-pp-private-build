import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / 'complete_executor_20261118' / 'runtime'))
from unittest.mock import patch

import owner_systemic_refill as relay
import owner_subagent_dispatcher as dispatcher
from owner_systemic_manifest_backend import (
    DispatcherManifestBackend, RuntimeBackendHold,
)
from owner_systemic_manifest_publisher import (
    _canonical, publish_reviewed_manifest,
)
from test_owner_systemic_manifest_publisher import MISSION, manifest


class Native:
    def __init__(self, config):
        self.config = config
        self.state = {"tasks": {}}
        self.ns = {"_qlock": threading.RLock()}
        self.stopped = False

    def owner_allowed(self): return True
    def stop_active(self): return self.stopped
    def writer_lease(self): return True


class BackendAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "nox"
        self.package = self.root / "state/dispatcher/project_executor/package"
        self.package.mkdir(parents=True)
        (self.root / "state/dispatcher").mkdir(parents=True, exist_ok=True)
        (self.root / "state").mkdir(exist_ok=True)
        (self.root / "state/owner_maintenance.lock").write_bytes(b"")
        (self.root / "state/owner_maintenance.lock").chmod(0o600)
        self.config_path = self.root / "config/owner_native_subagents.json"
        self.config_path.parent.mkdir(parents=True)
        self.db_path = self.root / "kb/knowledge.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self.registry_paths = {}
        for name, data in {
            "project_work_tasks.json": b'{"tasks":[]}',
            "project_work_ideas.json": b'{"ideas":[]}',
            "project_routing_4q.json": b'{"tasks":[]}',
            "project_work_receipts_source.json": b'{"receipts":[]}',
        }.items():
            path = self.root / "state/dispatcher" / name
            path.write_bytes(data)
            self.registry_paths[name] = path
        pins = {
            "tasks": hashlib.sha256(self.registry_paths["project_work_tasks.json"].read_bytes()).hexdigest(),
            "ideas": hashlib.sha256(self.registry_paths["project_work_ideas.json"].read_bytes()).hexdigest(),
            "routing": hashlib.sha256(self.registry_paths["project_routing_4q.json"].read_bytes()).hexdigest(),
            "receipts": hashlib.sha256(self.registry_paths["project_work_receipts_source.json"].read_bytes()).hexdigest(),
        }
        self.previous = manifest(1, None, [])
        self.previous["registry"]["source_registry_sha256"] = pins
        previous_raw = _canonical(self.previous)
        self.previous_sha = hashlib.sha256(previous_raw).hexdigest()
        relay_dir = self.package / "relay"
        relay_dir.mkdir()
        (relay_dir / (self.previous_sha + ".json")).write_bytes(previous_raw)
        candidate = manifest(2, self.previous_sha, [MISSION])
        candidate["registry"]["source_registry_sha256"] = pins
        self.candidate_raw = _canonical(candidate)
        self.candidate_sha = hashlib.sha256(self.candidate_raw).hexdigest()
        self.receipt = {
            "schema": "NOX_OWNER_REVIEW_RECEIPT_V1",
            "state": "OWNER_REVIEWED", "phase": "OWNER_REVIEWED_MANIFEST",
            "job_id": "review-17", "review_origin": "OWNER_REVIEWED",
            "owner_reviewed": True, "owner_request": "request-17",
            "source_sha256": "f" * 64,
            "previous_manifest_sha256": self.previous_sha,
            "manifest_sha256": self.candidate_sha,
            "source_registry_sha256": pins,
            "original_task_accepted": False,
        }
        encoded_receipt = dispatcher.encoded(self.receipt)
        self.receipt_sha = dispatcher.digest(encoded_receipt)
        text = dispatcher.memory_text(self.receipt)
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE s03_items (id INTEGER, text TEXT, meta TEXT, sha256 TEXT, segment TEXT, provenance TEXT)")
        conn.execute("INSERT INTO s03_items VALUES (1,?,?,?,?,?)", (
            text, json.dumps({"receipt": self.receipt}, sort_keys=True),
            dispatcher.digest(("M2|" + text).encode()), "M2", "owner_native_subagents"))
        conn.commit()
        conn.close()
        self.config = {
            "schema": dispatcher.SCHEMA, "owner_authorized": True,
            "owner_request": "request-17", "owner_source_sha": "f" * 64,
            "policy_id": dispatcher.POLICY_ID, "mode": "NORMAL", "target": 3,
            "execution_mode": "NATIVE_PROJECT_V1", "module_pins": {},
            "project_executor": {"package_root": str(self.package)},
            "systemic_relay": {"path": str(relay_dir / (self.previous_sha + ".json")),
                               "sha256": self.previous_sha},
        }
        self.config_path.write_bytes(dispatcher.encoded(self.config))
        self.config_path.chmod(0o600)
        self.patches = [
            patch.object(dispatcher, "ROOT", self.root),
            patch.object(dispatcher, "CONFIG", self.config_path),
            patch.object(dispatcher, "DB", self.db_path),
            patch.object(dispatcher, "PROJECT_FILES", {
                "work_tasks_sha256": self.registry_paths["project_work_tasks.json"],
                "work_ideas_sha256": self.registry_paths["project_work_ideas.json"],
                "routing_sha256": self.registry_paths["project_routing_4q.json"],
            }),
        ]
        self.native = Native(self.config)
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.tmp.cleanup()

    def test_exact_s03_owner_receipt_and_config_cas(self):
        backend = DispatcherManifestBackend(self.native)
        result = publish_reviewed_manifest(
            self.previous_sha, self.candidate_raw, self.receipt_sha, backend=backend)
        self.assertEqual(result["manifest_sha256"], self.candidate_sha)
        self.assertEqual(result["native_jobs_published"], 0)
        config = json.loads(self.config_path.read_bytes())
        self.assertEqual(config["systemic_relay"]["sha256"], self.candidate_sha)
        self.assertEqual((self.package / "relay" / (self.candidate_sha + ".json")).read_bytes(),
                         self.candidate_raw)

    def test_missing_or_malformed_s03_receipt_holds_before_config_cas(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE s03_items SET meta=?", (json.dumps({"receipt": {"phase": "wrong"}}),))
        conn.commit()
        conn.close()
        backend = DispatcherManifestBackend(self.native)
        with self.assertRaisesRegex(RuntimeBackendHold, "S03_RECEIPT_PROOF"):
            backend.verify_owner_review_receipt(self.receipt_sha)
        self.assertEqual(json.loads(self.config_path.read_bytes())["systemic_relay"]["sha256"],
                         self.previous_sha)

    def test_stop_gate_rejects_owner_lease(self):
        self.native.stopped = True
        backend = DispatcherManifestBackend(self.native)
        with self.assertRaisesRegex(RuntimeBackendHold, "STOP"):
            with backend.owner_publish_lease():
                self.fail("STOP must prevent entry")
