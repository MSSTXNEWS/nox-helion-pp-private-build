#!/usr/bin/env python3
"""Owner-requested, encrypted-only read of the two installed S03 source files.

This program never prints source, database rows, secrets, or raw exceptions. The
only transferable content is a bounded RSA-OAEP/AES-GCM envelope. It does not
write on the host and opens the SQLite database only in immutable read-only mode
when a path can be resolved statically from the attested source.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
import time
import urllib.parse
import zipfile
from io import BytesIO
from pathlib import Path

SCHEMA = "NOX_S03_SOURCE_EXPORT_V1"
ROOT = "/root/nox"
FILES = (
    ("chat_proxy.py", "/root/nox/scripts/chat_proxy.py",
     "cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb"),
    ("s03_memory.py", "/root/nox/scripts/s03_memory.py",
     "776a6dc25726540d75ec51216d1e333ca89b24e803ba3620f9b5e470a3c81476"),
)
MAX_FILE_BYTES = 256 * 1024
MAX_EXPORT_KEY_B64_CHARS = 12000
MAX_TOTAL_BYTES = 512 * 1024
MAX_ENVELOPE_BYTES = 1024 * 1024
CHUNK_BYTES = 9000
KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
TRANSFER_RE = re.compile(r"^[a-f0-9]{32}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def b64u_decode(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,12000}", value):
        raise ValueError("HOLD_SOURCE_EXPORT_KEY_FORMAT")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def load_export_key(encoded, now=None):
    """Validate public-only transfer key before touching host files."""
    try:
        raw = b64u_decode(encoded)
        value = json.loads(raw)
        if raw != canonical(value):
            raise ValueError
        required = {"schema", "scope", "key_id", "transfer_id", "created_at", "expires_at", "public_key_pem"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError
        if value["schema"] != "NOX_OWNER_SOURCE_EXPORT_KEY_V1" or value["scope"] != "NOX_S03_SOURCE_EXPORT_V1":
            raise ValueError
        if not KEY_RE.fullmatch(str(value["key_id"])) or not TRANSFER_RE.fullmatch(str(value["transfer_id"])):
            raise ValueError
        if type(value["created_at"]) is not int or type(value["expires_at"]) is not int:
            raise ValueError
        now = int(time.time()) if now is None else now
        if value["created_at"] > now + 300 or value["expires_at"] < now or value["expires_at"] - value["created_at"] > 3600:
            raise ValueError
        pem = value["public_key_pem"]
        if not isinstance(pem, str) or len(pem) > 12000 or not pem.startswith("-----BEGIN PUBLIC KEY-----\n"):
            raise ValueError
        if "PRIVATE KEY" in pem or not pem.rstrip().endswith("-----END PUBLIC KEY-----"):
            raise ValueError
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
        public_key = serialization.load_pem_public_key(pem.encode("ascii"))
        if not isinstance(public_key, RSAPublicKey) or public_key.key_size != 4096 or public_key.public_numbers().e != 65537:
            raise ValueError
        return value, public_key
    except ValueError as exc:
        if str(exc).startswith("HOLD_"):
            raise
        raise ValueError("HOLD_SOURCE_EXPORT_KEY_INVALID") from None
    except Exception:
        raise ValueError("HOLD_SOURCE_EXPORT_CRYPTO_OR_KEY_UNAVAILABLE") from None


def _safe_components(path):
    if not isinstance(path, str) or not path.startswith(ROOT + "/"):
        raise ValueError("HOLD_SOURCE_EXPORT_PATH_SCOPE")
    parts = Path(path).parts
    if ".." in parts or not parts or parts[0] != "/":
        raise ValueError("HOLD_SOURCE_EXPORT_PATH_SCOPE")
    return parts


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_uid, st.st_nlink)


def _open_fd(path, limit):
    parts = _safe_components(path)
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
            info = os.fstat(parent)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("HOLD_SOURCE_EXPORT_PARENT_UNSAFE")
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1 or before.st_mode & 0o022:
                raise ValueError("HOLD_SOURCE_EXPORT_FILE_UNSAFE")
            if before.st_size < 0 or before.st_size > limit:
                raise ValueError("HOLD_SOURCE_EXPORT_FILE_SIZE")
            os.close(parent)
            parent = -1
            return fd, before
        except BaseException:
            os.close(fd)
            raise
    except BaseException:
        if parent >= 0:
            os.close(parent)
        raise


def _open_readonly(path, limit):
    fd, before = _open_fd(path, limit)
    try:
        content = bytearray()
        while len(content) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(fd)
        if len(content) > limit or _identity(before) != _identity(after):
            raise ValueError("HOLD_SOURCE_EXPORT_FILE_CHANGED")
        os.lseek(fd, 0, os.SEEK_SET)
        second = bytearray()
        while len(second) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(second)))
            if not chunk:
                break
            second.extend(chunk)
        if bytes(content) != bytes(second):
            raise ValueError("HOLD_SOURCE_EXPORT_FILE_CHANGED")
        return bytes(content), fd, after
    except BaseException:
        os.close(fd)
        raise


def read_pinned_sources():
    result = []
    total = 0
    for name, path, expected in FILES:
        raw, fd, info = _open_readonly(path, MAX_FILE_BYTES)
        try:
            digest = hashlib.sha256(raw).hexdigest()
            if digest != expected:
                raise ValueError("HOLD_SOURCE_EXPORT_SOURCE_HASH_MISMATCH")
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("HOLD_SOURCE_EXPORT_TOTAL_SIZE")
            result.append((name, raw, digest, info))
        finally:
            os.close(fd)
    return result


def _literal(node, names):
    """Small AST-only evaluator for constant SQLite path expressions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        left, right = _literal(node.left, names), _literal(node.right, names)
        if not isinstance(left, str) or not isinstance(right, str):
            return None
        return left + right if isinstance(node.op, ast.Add) else str(Path(left) / right)
    if isinstance(node, ast.Call):
        function = node.func
        if isinstance(function, ast.Name) and function.id == "Path" and len(node.args) == 1:
            value = _literal(node.args[0], names)
            return value if isinstance(value, str) else None
        if isinstance(function, ast.Attribute) and function.attr == "join" and isinstance(function.value, ast.Attribute) and function.value.attr == "path":
            args = [_literal(arg, names) for arg in node.args]
            if args and all(isinstance(x, str) for x in args):
                return os.path.join(*args)
    return None


def resolve_db_path(source):
    try:
        tree = ast.parse(source.decode("utf-8"))
    except Exception:
        return None
    names = {}
    for _ in range(6):
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = _literal(node.value, names)
                if isinstance(value, str):
                    for target in targets:
                        if isinstance(target, ast.Name):
                            names[target.id] = value
    candidates = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_connect = (isinstance(func, ast.Attribute) and func.attr == "connect"
                      and isinstance(func.value, ast.Name) and func.value.id == "sqlite3")
        if is_connect and node.args:
            value = _literal(node.args[0], names)
            if isinstance(value, str) and os.path.isabs(value) and (value == ROOT or value.startswith(ROOT + "/")):
                candidates.add(os.path.normpath(value))
    return next(iter(candidates)) if len(candidates) == 1 else None


def read_schema_metadata(source):
    """Read SQLite DDL metadata only; no application table rows or defaults."""
    path = resolve_db_path(source)
    if path is None:
        return {"status": "UNRESOLVED_STATIC_DB_PATH"}
    fd = None
    conn = None
    try:
        fd, before = _open_fd(path, 2**63 - 1)
        uri = "file:" + urllib.parse.quote(f"/proc/self/fd/{fd}", safe="/") + "?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True, timeout=1)
        conn.execute("PRAGMA query_only=ON")
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        if len(tables) > 100:
            raise ValueError("HOLD_SOURCE_EXPORT_SCHEMA_BOUNDS")
        output = []
        count = 0
        for table in tables:
            if not isinstance(table, str) or len(table) > 128 or "\x00" in table:
                raise ValueError("HOLD_SOURCE_EXPORT_SCHEMA_BOUNDS")
            quoted = '"' + table.replace('"', '""') + '"'
            columns = []
            for _, name, data_type, notnull, _default, primary_key in conn.execute(f"PRAGMA table_info({quoted})"):
                count += 1
                if count > 500:
                    raise ValueError("HOLD_SOURCE_EXPORT_SCHEMA_BOUNDS")
                columns.append({"name": str(name)[:128], "type": str(data_type)[:128],
                                "notnull": bool(notnull), "primary_key": int(primary_key)})
            indexes = []
            for _, index_name, unique, origin, partial in conn.execute(f"PRAGMA index_list({quoted})"):
                if not isinstance(index_name, str) or len(index_name) > 128:
                    raise ValueError("HOLD_SOURCE_EXPORT_SCHEMA_BOUNDS")
                index_quoted = '"' + index_name.replace('"', '""') + '"'
                index_columns = [str(row[2])[:128] if row[2] is not None else None
                                 for row in conn.execute(f"PRAGMA index_info({index_quoted})")]
                count += len(index_columns)
                if count > 500:
                    raise ValueError("HOLD_SOURCE_EXPORT_SCHEMA_BOUNDS")
                indexes.append({"name": index_name, "unique": bool(unique), "origin": str(origin)[:16],
                                "partial": bool(partial), "columns": index_columns})
            foreign_keys = []
            for _, sequence, target_table, from_column, to_column, on_update, on_delete, match in conn.execute(f"PRAGMA foreign_key_list({quoted})"):
                foreign_keys.append({"sequence": int(sequence), "table": str(target_table)[:128],
                                     "from": str(from_column)[:128] if from_column is not None else None,
                                     "to": str(to_column)[:128] if to_column is not None else None,
                                     "on_update": str(on_update)[:16], "on_delete": str(on_delete)[:16],
                                     "match": str(match)[:16]})
            count += len(foreign_keys)
            if count > 500:
                raise ValueError("HOLD_SOURCE_EXPORT_SCHEMA_BOUNDS")
            output.append({"name": table, "columns": columns, "indexes": indexes, "foreign_keys": foreign_keys})
        after = os.fstat(fd)
        if _identity(before) != _identity(after):
            raise ValueError("HOLD_SOURCE_EXPORT_SCHEMA_CHANGED")
        schema = {"status": "READ_ONLY_SCHEMA_CAPTURED", "database_basename": Path(path).name, "tables": output}
        schema["schema_sha256"] = hashlib.sha256(canonical(schema)).hexdigest()
        return schema
    except ValueError:
        raise
    except Exception:
        return {"status": "SCHEMA_READ_UNAVAILABLE"}
    finally:
        if conn is not None:
            conn.close()
        if fd is not None:
            os.close(fd)


def make_envelope(encoded_key, request_id, source_sha, sources, schema=None, now=None):
    key_info, public_key = load_export_key(encoded_key, now=now)
    if not isinstance(request_id, int) or request_id <= 0 or not SHA_RE.fullmatch(source_sha or ""):
        raise ValueError("HOLD_SOURCE_EXPORT_REQUEST_BINDING")
    schema = schema if schema is not None else read_schema_metadata(next(raw for name, raw, *_ in sources if name == "s03_memory.py"))
    manifest = {"schema": SCHEMA, "request_id": request_id, "source_sha": source_sha,
                "transfer_id": key_info["transfer_id"], "key_id": key_info["key_id"],
                "created_at": int(time.time() if now is None else now),
                "files": [{"name": name, "size": len(raw), "sha256": digest}
                          for name, raw, digest, _ in sources],
                "sqlite_schema": schema}
    bundle = BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw, _, _ in sources:
            archive.writestr(name, raw)
        archive.writestr("manifest.json", canonical(manifest))
    plaintext = bundle.getvalue()
    bundle_sha = hashlib.sha256(plaintext).hexdigest()
    aad_obj = {"schema": SCHEMA, "request_id": request_id, "source_sha": source_sha,
               "transfer_id": key_info["transfer_id"], "key_id": key_info["key_id"], "bundle_sha256": bundle_sha}
    aad = canonical(aad_obj)
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aes_key, nonce = secrets.token_bytes(32), secrets.token_bytes(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, aad)
    wrapped = public_key.encrypt(aes_key, OAEP(mgf=MGF1(algorithm=hashes.SHA256()),
                                               algorithm=hashes.SHA256(), label=None))
    envelope = {**aad_obj, "schema": "NOX_ENCRYPTED_SOURCE_EXPORT_ENVELOPE_V1",
                "aad_b64": base64.b64encode(aad).decode("ascii"),
                "wrapped_key_b64": base64.b64encode(wrapped).decode("ascii"),
                "nonce_b64": base64.b64encode(nonce).decode("ascii"),
                "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii")}
    encoded = canonical(envelope)
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise ValueError("HOLD_SOURCE_EXPORT_ENVELOPE_SIZE")
    return encoded, {"request_id": request_id, "source_sha": source_sha,
                     "transfer_id": key_info["transfer_id"], "key_id": key_info["key_id"],
                     "envelope_bytes": len(encoded), "envelope_sha256": hashlib.sha256(encoded).hexdigest(),
                     "file_count": len(sources), "sqlite_schema_status": schema.get("status")}


def read_export_key_stdin():
    """Read the bounded public-key payload only from private stdin."""
    if "NOX_OWNER_EXPORT_KEY_B64" in os.environ:
        raise ValueError("HOLD_SOURCE_EXPORT_KEY_ENV_FORBIDDEN")
    encoded_key = sys.stdin.read(MAX_EXPORT_KEY_B64_CHARS + 1)
    if not encoded_key or len(encoded_key) > MAX_EXPORT_KEY_B64_CHARS:
        raise ValueError("HOLD_SOURCE_EXPORT_KEY_STDIN_BOUNDS")
    return encoded_key


def run():
    # The private key is never accepted here; public material arrives only on stdin.
    encoded_key = read_export_key_stdin()
    request_id_raw = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    if not request_id_raw.isdigit() or not SHA_RE.fullmatch(source_sha):
        raise ValueError("HOLD_SOURCE_EXPORT_REQUEST_BINDING")
    # Validate cryptographic support and the public key before opening target files.
    load_export_key(encoded_key)
    sources = read_pinned_sources()
    envelope, receipt = make_envelope(encoded_key, int(request_id_raw), source_sha, sources)
    transfer_id = receipt["transfer_id"]
    total = (len(envelope) + CHUNK_BYTES - 1) // CHUNK_BYTES
    print("NOX_MAINT_SOURCE_EXPORT_META=" + json.dumps({
        "schema": "NOX_SOURCE_EXPORT_TRANSFER_V1", "request_id": receipt["request_id"],
        "source_sha": receipt["source_sha"], "transfer_id": transfer_id,
        "key_id": receipt["key_id"], "total_bytes": len(envelope), "total_chunks": total,
        "envelope_sha256": receipt["envelope_sha256"]}, sort_keys=True, separators=(",", ":")), flush=True)
    for index in range(total):
        chunk = envelope[index * CHUNK_BYTES:(index + 1) * CHUNK_BYTES]
        print("NOX_MAINT_SOURCE_EXPORT_CHUNK=" + json.dumps({
            "transfer_id": transfer_id, "index": index, "data_b64": base64.b64encode(chunk).decode("ascii")},
            sort_keys=True, separators=(",", ":")), flush=True)
    print("NOX_MAINT_SOURCE_EXPORT_COMPLETE=true", flush=True)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r"HOLD_[A-Z0-9_]+", code):
            code = "HOLD_SOURCE_EXPORT_INTERNAL"
        print("NOX_MAINT_SOURCE_EXPORT_RESULT=" + code, flush=True)
        raise SystemExit(2)
