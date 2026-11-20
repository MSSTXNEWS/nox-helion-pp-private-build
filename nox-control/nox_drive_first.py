#!/usr/bin/env python3
"""NOX Drive-first transport: HTTPS -> Google Drive, or local warm weight -> Drive.

Uses the existing rclone Google Drive remote plus its native chunker overlay.
No download of a full model to local SSD. No deletion, shell, credentials,
native job insertion, or weight loading. Requires exact owner-pinned manifest.
"""
from __future__ import annotations
import argparse
import configparser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT_ID = "1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v"
SCHEMA = "nox.drive.first.v1"
RECEIPT_SCHEMA = "nox.drive.first.verified.v1"
CONFIG = Path("/root/.config/rclone/rclone.conf")
STATE = Path("/var/lib/nox-drive-first")
DEST_ROOT = "noxdrive:NOX_WEIGHT_CHUNKS"
CHUNKER = "noxchunks"
CHUNK = "1Gi"
MIB = 1024 ** 2
MIN_RAM = 384 * MIB
BLOCK = MIB
MAX_MANIFEST = 16384
MAX_FILE = 5 * 1024 ** 4
SHA = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}\Z")
SUFFIX = re.compile(r"(?:\.gguf|\.safetensors|\.bin|\.pt|\.pth|\.part\d\d)\Z", re.I)
LOCAL_ROOTS = (Path("/root/nox/models"), Path("/root/nox/weights"),
               Path("/root/nox/teachers_ondisk"), Path("/workspace/models"))
SOURCE_HOSTS = frozenset((
    "huggingface.co", "cdn-lfs.hf.co", "cas-bridge.xethub.hf.co",
    "github.com", "objects.githubusercontent.com",
    "release-assets.githubusercontent.com", "download.pytorch.org",
    "storage.googleapis.com",
))
STOPS = ("/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP",
         "/root/nox/state/DRIVE_STOP.flag",
         "/root/nox/state/OWNER_MAINTENANCE.flag", "/workspace/NOX_STOP")
BLOCKED = frozenset(("s03", "checkpoint", "checkpoints", "training",
                     "optimizer", "database", "sqlite", "personal", "private"))


class Hold(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Hold("HOLD_DRIVE_FIRST_" + reason)


def stop_clear(stops=STOPS):
    require(not any(os.path.lexists(v) for v in stops), "STOP")


def private_file(path, *, max_bytes=MAX_MANIFEST):
    p = Path(os.path.abspath(path))
    require(p.is_file() and not p.is_symlink()
            and not any(q.is_symlink() for q in p.parents), "FILE")
    st = p.stat()
    require(st.st_uid == os.geteuid() and st.st_nlink == 1
            and not st.st_mode & 0o077 and 0 < st.st_size <= max_bytes, "FILE_PERMISSIONS")
    return p


def private_dir(path):
    p = Path(os.path.abspath(path))
    require(p.is_dir() and not p.is_symlink()
            and not any(q.is_symlink() for q in p.parents), "STATE_DIR")
    st = p.stat()
    require(st.st_uid == os.geteuid() and not st.st_mode & 0o077, "STATE_PERMISSIONS")
    return p


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * MIB), b""):
            h.update(b)
    return h.hexdigest()


def cgroup_admit(root=Path("/sys/fs/cgroup"), min_free=MIN_RAM):
    try:
        maximum = (root / "memory.max").read_text().strip()
        current = int((root / "memory.current").read_text().strip())
        require(maximum != "max", "CGROUP_UNKNOWN")
        raw_free = int(maximum) - current
    except (OSError, ValueError):
        raise Hold("HOLD_DRIVE_FIRST_CGROUP_UNKNOWN") from None
    require(raw_free >= min_free, "CGROUP_BUSY")
    return raw_free


def load_manifest(path, expected):
    require(isinstance(expected, str) and SHA.fullmatch(expected) is not None,
            "MANIFEST_PIN")
    raw = private_file(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "MANIFEST_CHANGED")
    try:
        m = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Hold("HOLD_DRIVE_FIRST_MANIFEST_JSON") from None
    require(isinstance(m, dict)
            and set(m) in ({"schema", "task_id", "action", "name", "size", "sha256",
                            "approved", "source_path"},
                           {"schema", "task_id", "action", "name", "size", "sha256",
                            "approved", "source_url"}), "MANIFEST_SHAPE")
    require(m["schema"] == SCHEMA and m["approved"] is True, "MANIFEST_APPROVAL")
    require(isinstance(m["task_id"], str) and ID.fullmatch(m["task_id"]) is not None,
            "TASK_ID")
    require(isinstance(m["name"], str) and NAME.fullmatch(m["name"]) is not None
            and SUFFIX.search(m["name"]) is not None
            and not any(part.lower() in BLOCKED for part in m["name"].split(".")),
            "NAME")
    require(type(m["size"]) is int and 0 < m["size"] <= MAX_FILE, "SIZE")
    require(isinstance(m["sha256"], str) and SHA.fullmatch(m["sha256"]) is not None,
            "SHA")
    if m["action"] == "offload":
        require("source_path" in m, "SOURCE_PATH")
    elif m["action"] == "ingest":
        require("source_url" in m and https_allowed(m["source_url"]), "SOURCE_URL")
    else:
        raise Hold("HOLD_DRIVE_FIRST_ACTION")
    return m


def https_allowed(url):
    if not isinstance(url, str) or len(url) > 8192:
        return False
    try:
        p = urllib.parse.urlsplit(url)
        return (p.scheme == "https" and p.hostname in SOURCE_HOSTS
                and p.port in (None, 443) and not p.username and not p.password
                and not p.fragment)
    except ValueError:
        return False


class VerifiedRedirect(urllib.request.HTTPRedirectHandler):
    """Only known public download/CDN hosts, never local or arbitrary redirects."""
    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        require(self.count <= 5 and https_allowed(newurl), "URL_REDIRECT")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_config(path):
    p = private_file(path, max_bytes=131072)
    cfg = configparser.RawConfigParser(interpolation=None)
    try:
        cfg.read_string(p.read_text(encoding="utf-8"))
    except (OSError, configparser.Error, UnicodeError):
        raise Hold("HOLD_DRIVE_FIRST_CONFIG_PARSE") from None
    require(cfg.has_section("noxdrive"), "CONFIG_MISSING_REMOTE")
    get = lambda n, k: cfg.get(n, k, fallback="").strip()
    require(get("noxdrive", "type") == "drive"
            and get("noxdrive", "root_folder_id") == ROOT_ID
            and any(get("noxdrive", v) for v in
                    ("token", "service_account_file", "service_account_credentials")),
            "GOOGLE_AUTH_REQUIRED")
    require(cfg.has_section(CHUNKER)
            and get(CHUNKER, "type") == "chunker"
            and get(CHUNKER, "remote") == DEST_ROOT
            and get(CHUNKER, "chunk_size") == CHUNK
            and get(CHUNKER, "hash_type") == "md5", "CHUNKER_CONFIG_REQUIRED")
    return p


def ensure_chunker(config):
    """Create the standard chunker overlay only after owner OAuth is configured.

    rclone owns config serialization; this function never touches the OAuth token.
    A preexisting differently configured overlay must never be overwritten.
    """
    try:
        return validate_config(config)
    except Hold as err:
        if str(err) != "HOLD_DRIVE_FIRST_CHUNKER_CONFIG_REQUIRED":
            raise
    config = private_file(config, max_bytes=131072)
    cfg = configparser.RawConfigParser(interpolation=None)
    try:
        cfg.read_string(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, configparser.Error):
        raise Hold("HOLD_DRIVE_FIRST_CONFIG_PARSE") from None
    require(not cfg.has_section(CHUNKER), "CHUNKER_CONFLICT")
    stop_clear()
    cgroup_admit()
    run_rclone(["config", "create", CHUNKER, "chunker",
                "remote", DEST_ROOT, "chunk_size", CHUNK,
                "hash_type", "md5"], config, timeout=60)
    return validate_config(config)


def safe_local_source(file, roots=LOCAL_ROOTS):
    p = Path(os.path.abspath(file))
    require(p.is_file() and not p.is_symlink()
            and not any(q.is_symlink() for q in p.parents)
            and p.stat().st_nlink == 1, "SOURCE_FILE")
    require(any(p.is_relative_to(root) for root in roots), "SOURCE_OUTSIDE_MODELS")
    require(not any(part.lower() in BLOCKED for part in p.parts)
            and SUFFIX.search(p.name) is not None, "SOURCE_PROTECTED")
    return p


def run_rclone(args, config, *, timeout=8 * 3600, run=subprocess.run):
    stop_clear()
    require(bool(shutil.which("rclone")), "RCLONE_MISSING")
    try:
        # Never print subprocess output, command, signed URLs or token-bearing config.
        proc = run(["rclone", "--config", str(config), *args],
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise Hold("HOLD_DRIVE_FIRST_RCLONE_EXECUTION") from None
    require(proc.returncode == 0, "RCLONE_FAILED")
    stop_clear()


def verify_remote(remote, *, config, size, digest):
    """Independently stream the logical chunker file; O(1 MiB) RAM."""
    h = hashlib.sha256()
    n = 0
    proc = subprocess.Popen(["rclone", "--config", str(config), "cat", remote,
                             "--retries", "2", "--low-level-retries", "2"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            stop_clear()
            b = proc.stdout.read(BLOCK)
            if not b:
                break
            n += len(b)
            require(n <= size, "REMOTE_SIZE")
            h.update(b)
        require(proc.wait(timeout=30) == 0 and n == size and
                h.hexdigest() == digest, "REMOTE_SHA")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if proc.stdout:
            proc.stdout.close()


def stream_https(m, target, config):
    """Direct HTTP response -> rclone rcat --size; no complete local spool."""
    opener = urllib.request.build_opener(VerifiedRedirect())
    request = urllib.request.Request(m["source_url"],
                                     headers={"User-Agent": "NOX-Drive-First/1"})
    h = hashlib.sha256()
    written = 0
    child = None
    try:
        with opener.open(request, timeout=30) as response:
            require(response.status == 200 and https_allowed(response.geturl()), "HTTPS_RESPONSE")
            header = response.headers.get("Content-Length")
            require(header is None or
                    (header.isdecimal() and int(header) == m["size"]), "HTTPS_SIZE")
            child = subprocess.Popen(
                ["rclone", "--config", str(config), "rcat", target,
                 "--size", str(m["size"]), "--streaming-upload-cutoff", "8M",
                 "--retries", "2", "--low-level-retries", "2"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            while True:
                stop_clear()
                cgroup_admit()
                data = response.read(BLOCK)
                if not data:
                    break
                written += len(data)
                require(written <= m["size"], "HTTPS_OVERFLOW")
                h.update(data)
                try:
                    child.stdin.write(data)
                except (BrokenPipeError, OSError):
                    raise Hold("HOLD_DRIVE_FIRST_UPLOAD_DISCONNECTED") from None
            child.stdin.close()
            require(child.wait(timeout=120) == 0, "STREAM_UPLOAD")
        require(written == m["size"] and h.hexdigest() == m["sha256"],
                "SOURCE_SHA")
    except (OSError, urllib.error.URLError):
        raise Hold("HOLD_DRIVE_FIRST_HTTPS_TRANSPORT") from None
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def receipt(state, m, stage, dest):
    record = {
        "schema": RECEIPT_SCHEMA, "state": state, "task_id": m["task_id"],
        "name": m["name"], "action": m["action"], "bytes": m["size"],
        "sha256": m["sha256"], "staged": stage, "remote": dest,
        "remote_readback_verified": state == "VERIFIED_IN_DRIVE",
        "local_source_deleted": False, "chunked_transparently": True,
        "checked_at_unix": int(time.time()),
    }
    return record


def save_receipt(path, value):
    data = (json.dumps(value, sort_keys=True) + "\n").encode()
    # A killed transfer may leave an uncommitted .new file. A per-attempt
    # private O_EXCL tempfile prevents that orphan from permanently blocking
    # an otherwise unclaimed TaskID. The final receipt is still create-only.
    fd, temp_name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".new", dir=path.parent)
    tmp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        # A prior task receipt is immutable; a reused TaskID must not replace
        # evidence from a different source SHA or authorization epoch.
        try:
            os.link(tmp, path, follow_symlinks=False)
        except FileExistsError:
            raise Hold("HOLD_DRIVE_FIRST_RECEIPT_ALREADY_EXISTS") from None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)


def execute(m, config, state):
    stop_clear()
    cgroup_admit()
    # Acquire the existing task lock before any shared rclone config mutation.
    # In particular, an already receipted TaskID must never create a chunker.
    state = private_dir(state)
    lock = os.open(state / ".drive-first.lock",
                   os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(lock, "r+b") as handle:
            st = os.fstat(handle.fileno())
            require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
                    and st.st_nlink == 1 and not st.st_mode & 0o077, "LOCK")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Hold("HOLD_DRIVE_FIRST_BUSY")
            # Replay is not a new transfer: refuse a TaskID with any existing
            # receipt before touching the Google Drive transport.
            receipt_path = state / ("drive-" + m["task_id"] + ".json")
            require(not os.path.lexists(receipt_path), "RECEIPT_ALREADY_EXISTS")
            # The owner-scoped lock also fences the optional rclone overlay
            # setup. A replay or concurrent worker cannot mutate credentials.
            config = ensure_chunker(config)
            # Exercise the pinned Google Drive root, never enumerate/print files.
            run_rclone(["lsf", "noxdrive:", "--max-depth", "1", "--retries", "1",
                        "--low-level-retries", "1"], config, timeout=30)
            name = m["name"]
            namespace = "WARM" if m["action"] == "offload" else "DOWNLOADS"
            final = f"{CHUNKER}:{namespace}/{name}"
            stage = f"{CHUNKER}:STAGING/{m['task_id']}-{m['sha256'][:20]}-{name}"
            if m["action"] == "offload":
                source = safe_local_source(m["source_path"])
                require(source.stat().st_size == m["size"] and
                        sha_file(source) == m["sha256"], "LOCAL_SOURCE_SHA")
                run_rclone(["copyto", str(source), stage, "--immutable",
                            "--retries", "3", "--low-level-retries", "3",
                            "--transfers", "1", "--tpslimit", "4"], config)
            else:
                stream_https(m, stage, config)
            verify_remote(stage, config=config, size=m["size"], digest=m["sha256"])
            stop_clear()
            # No remote overwrite of existing final weights, even on retry.
            run_rclone(["moveto", stage, final, "--immutable",
                        "--retries", "2"], config)
            verify_remote(final, config=config, size=m["size"], digest=m["sha256"])
            if m["action"] == "offload":
                require(source.stat().st_size == m["size"] and
                        sha_file(source) == m["sha256"], "SOURCE_CHANGED_AFTER_UPLOAD")
            value = receipt("VERIFIED_IN_DRIVE", m, stage, final)
            save_receipt(receipt_path, value)
            return {"schema": SCHEMA, "state": "VERIFIED_IN_DRIVE",
                    "task_id": m["task_id"], "readback_verified": True,
                    "source_deleted": False}
    finally:
        # with os.fdopen closes the lock; we never remove another owner's lock.
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha", required=True)
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--state-dir", default=str(STATE))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        m = load_manifest(args.manifest, args.manifest_sha)
        if not args.execute:
            result = {"schema": SCHEMA, "state": "PLAN_ONLY",
                      "task_id": m["task_id"], "action": m["action"],
                      "size": m["size"], "destination": CHUNKER,
                      "needs_authorized_google": True,
                      "native_job_started": False}
        else:
            result = execute(m, args.config, args.state_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Hold as exc:
        # No URL, token, file path, private provider errors or remote names.
        print(json.dumps({"schema": SCHEMA, "state": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
