"""Concrete backend for the fail-closed reviewed-manifest publisher.

Uses the existing native dispatcher's owner gate and writer lease, the
existing exclusive owner_maintenance.lock, content-addressed package storage,
read-only exact S03 receipt lookup, and owner config atomic write/readback.
This backend never submits native tasks.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import stat

import owner_subagent_dispatcher as dispatcher


class RuntimeBackendHold(RuntimeError):
    pass


class DispatcherManifestBackend:
    def __init__(self, native):
        self.native = native
        self.package = Path(native.config["project_executor"]["package_root"])
        self._fd = None
        self._initial_config_raw = None
        self._initial_config = None

    def _hold(self, code):
        raise RuntimeBackendHold("HOLD_REVIEWED_MANIFEST_BACKEND_" + code)

    def _guard(self):
        if self.native.owner_allowed() is not True:
            self._hold("OWNER_SCOPE")
        if self.native.stop_active() is not False:
            self._hold("STOP")
        if self.native.writer_lease() is not True:
            self._hold("WRITER_LEASE")

    def _config(self):
        path = dispatcher.plain(dispatcher.CONFIG)
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            self._hold("CONFIG_OWNER_MODE")
        raw = dispatcher.read(path, 262144)
        value = json.loads(raw)
        if not isinstance(value, dict):
            self._hold("CONFIG_SCHEMA")
        return raw, value

    def owner_allowed(self):
        return self.native.owner_allowed()

    def stop_active(self):
        return self.native.stop_active()

    def writer_lease(self):
        return self.native.writer_lease()

    def owner_publish_lease(self):
        path = dispatcher.plain(dispatcher.ROOT / "state/owner_maintenance.lock")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info, named = os.fstat(fd), path.stat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o022
                    or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
                os.close(fd)
                self._hold("MAINTENANCE_IDENTITY")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if "fd" in locals():
                os.close(fd)
            self._hold("MAINTENANCE_BUSY")
        self._fd = fd
        try:
            self._guard()
            yield
        finally:
            self._fd = None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def current_manifest_reference(self):
        self._guard()
        raw, current = self._config()
        baseline = {k: v for k, v in self.native.config.items()
                    if k != "systemic_relay"}
        observed = {k: v for k, v in current.items()
                    if k != "systemic_relay"}
        if observed != baseline:
            self._hold("CONFIG_SCOPE_CHANGED")
        reference = current.get("systemic_relay")
        if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            self._hold("MANIFEST_REFERENCE")
        self._initial_config_raw, self._initial_config = raw, current
        expected = self.manifest_reference_for_sha(reference["sha256"])
        if reference != expected:
            self._hold("MANIFEST_REFERENCE_PATH")
        return reference

    def read_manifest_bytes(self, sha):
        path = self.manifest_reference_for_sha(sha)["path"]
        raw = dispatcher.read(Path(path), 1024 * 1024)
        if dispatcher.digest(raw) != sha:
            self._hold("MANIFEST_SHA")
        return raw

    def verify_owner_review_receipt(self, sha):
        if not dispatcher.SHA.fullmatch(str(sha)):
            self._hold("RECEIPT_SHA")
        pattern = "% receipt_sha256 " + sha
        with dispatcher.s03_connection() as conn:
            rows = conn.execute(
                "SELECT text,meta,sha256 FROM s03_items "
                "WHERE segment='M2' AND provenance=? AND text LIKE ? LIMIT 2",
                ("owner_native_subagents", pattern)).fetchall()
        if len(rows) != 1:
            self._hold("S03_RECEIPT_CARDINALITY")
        text, meta_raw, row_sha = rows[0]
        try:
            meta = json.loads(meta_raw)
            receipt = meta["receipt"]
        except (TypeError, ValueError, KeyError):
            self._hold("S03_RECEIPT_SCHEMA")
        raw = dispatcher.encoded(receipt)
        config = self._initial_config or self._config()[1]
        if (dispatcher.digest(raw) != sha
                or text != dispatcher.memory_text(receipt)
                or row_sha != dispatcher.digest(("M2|" + text).encode())
                or receipt.get("schema") != "NOX_OWNER_REVIEW_RECEIPT_V1"
                or receipt.get("phase") != "OWNER_REVIEWED_MANIFEST"
                or receipt.get("state") != "OWNER_REVIEWED"
                or receipt.get("review_origin") != "OWNER_REVIEWED"
                or receipt.get("owner_reviewed") is not True
                or receipt.get("owner_request") != config.get("owner_request")
                or receipt.get("source_sha256") != config.get("owner_source_sha")
                or receipt.get("original_task_accepted") is not False):
            self._hold("S03_RECEIPT_PROOF")
        return raw

    def live_source_registry_pins(self):
        pins = {}
        for key, path in dispatcher.PROJECT_FILES.items():
            registry_key = key.removesuffix("_sha256")
            pins[registry_key] = dispatcher.digest(dispatcher.read(path, 16 * 1024 * 1024))
        if set(pins) != {"tasks", "ideas", "routing"}:
            self._hold("REGISTRY_PATHS")
        receipt_path = dispatcher.ROOT / "state/dispatcher/project_work_receipts_source.json"
        pins["receipts"] = dispatcher.digest(dispatcher.read(receipt_path, 16 * 1024 * 1024))
        return pins

    def admitted_task_ids(self):
        with self.native.ns["_qlock"]:
            tasks = (self.native.state or {}).get("tasks", {})
            if not isinstance(tasks, dict):
                self._hold("QUEUE_SNAPSHOT")
            return set(tasks)

    def manifest_reference_for_sha(self, sha):
        path = self.package / "relay" / (sha + ".json")
        dispatcher.plain(path)
        return {"path": str(path), "sha256": sha}

    def write_content_addressed_manifest(self, path, sha, raw):
        self._guard()
        expected = self.manifest_reference_for_sha(sha)
        if path != expected["path"] or dispatcher.digest(raw) != sha:
            self._hold("CONTENT_ADDRESS_INPUT")
        target = Path(path)
        try:
            existing = dispatcher.read(target, 1024 * 1024)
        except FileNotFoundError:
            dispatcher.project_executor.write_atomic(target, raw)
            existing = dispatcher.read(target, 1024 * 1024)
        if existing != raw:
            self._hold("CONTENT_ADDRESS_COLLISION")
        return existing

    def compare_and_swap_systemic_relay(self, expected_sha, reference, receipt_sha):
        self._guard()
        raw, latest = self._config()
        if raw != self._initial_config_raw:
            self._hold("CONFIG_CAS_PREIMAGE")
        old_ref = latest.get("systemic_relay")
        if (not isinstance(old_ref, dict) or old_ref.get("sha256") != expected_sha
                or reference != self.manifest_reference_for_sha(reference.get("sha256", ""))):
            self._hold("CONFIG_CAS_EXPECTED")
        updated = dict(latest)
        updated["systemic_relay"] = reference
        new_raw = dispatcher.encoded(updated)
        self._guard()
        raw_now, _ = self._config()
        if raw_now != raw:
            self._hold("CONFIG_CAS_RACE")
        dispatcher.project_executor.write_atomic(dispatcher.CONFIG, new_raw)
        readback = dispatcher.read(dispatcher.CONFIG, 262144)
        if readback != new_raw:
            self._hold("CONFIG_CAS_READBACK")
        return dict(reference)

    def read_current_manifest_reference(self):
        return self._config()[1].get("systemic_relay")
