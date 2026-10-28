"""P04 Python-host compatibility port of the ONE local RAG index.

Use ONLY when the canonical NOX host is Python; do not activate alongside the
C# RagService. JSON schema and SHA-256 chunk/source identities match the
existing P04 index. Host #6 owns admission, SID mapping and single-bridge setup.
No new server, model downloader, database or external API.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
import stat
from pathlib import Path
import re
import threading
import time
from typing import Callable
from urllib.parse import quote, urlsplit
from urllib.request import (HTTPRedirectHandler, ProxyHandler, Request, build_opener)

INDEX_SCHEMA = "NOX-RAG-INDEX-v1"
MAX_BYTES = 256 * 1024 * 1024
MAX_SOURCE_CHARS = 2_000_000
MAX_QUERY_CHARS = 16_000
MAX_DIMENSIONS = 16_384
MAX_CONTEXT_CHARS = 24_000
MAX_EMBED_REPLY = 16 * 1024 * 1024
CHUNK_SIZE = 1200
OVERLAP = 120
SID_RE = re.compile(r"S-1-[0-9]{1,15}(?:-[0-9]{1,10}){1,15}\Z")
SHA_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class RagHold(ValueError):
    """Fail-closed input, index, model or provenance error."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RagHold("OLLAMA_REDIRECT_BLOCKED")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_reparse_ancestors(candidate: Path) -> None:
    """Deny symlinks and Windows reparse/junction ancestors before filesystem I/O.

    Native host #6 must still supply a trusted data root / picker and guard
    against path substitution races. This is a fail-closed preflight check.
    """
    for ancestor in (candidate, *candidate.parents):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RagHold("RAG_ANCESTOR_UNREADABLE") from exc
        if (stat.S_ISLNK(info.st_mode) or
                (getattr(info, "st_file_attributes", 0) &
                 getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))):
            raise RagHold("RAG_ANCESTOR_REPARSE_BLOCKED")


def _scope(owner_sid: str, conversation_id: str) -> None:
    if not isinstance(owner_sid, str) or len(owner_sid) > 184 or not SID_RE.fullmatch(owner_sid):
        raise RagHold("RAG_AUTHENTICATED_OWNER_SID_REQUIRED")
    if (not isinstance(conversation_id, str) or not conversation_id
            or len(conversation_id) > 256 or any(ord(c) < 32 for c in conversation_id)):
        raise RagHold("RAG_CONVERSATION_ID_INVALID")


def _safe_name(value: str) -> None:
    if (not isinstance(value, str) or not 0 < len(value) <= 255
            or Path(value).name != value or "/" in value or "\\" in value
            or value.lower().endswith((".txt", ".md")) is False
            or any(ord(c) < 32 for c in value)):
        raise RagHold("RAG_FILENAME_INVALID")


def _chunks(text: str):
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            split = max((text.rfind(ch, start + CHUNK_SIZE // 2, end) for ch in " \n\r\t"), default=-1)
            if split > start + CHUNK_SIZE // 2:
                end = split
        block = text[start:end].strip()
        if block:
            yield block
        if end == len(text):
            break
        start = max(start + 1, end - OVERLAP)


class LocalRag:
    """One host-activated local RAG implementation, shared JSON index schema."""

    def __init__(self, ollama_url: str, embedding_model: str, index_path: str | Path):
        if not isinstance(ollama_url, str):
            raise RagHold("OLLAMA_LOOPBACK_URL_REQUIRED")
        parsed = urlsplit(ollama_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/") or not parsed.port):
            raise RagHold("OLLAMA_LOOPBACK_ONLY")
        if (not isinstance(embedding_model, str) or not 0 < len(embedding_model) <= 256
                or any(ord(c) < 32 for c in embedding_model)):
            raise RagHold("EMBEDDING_MODEL_REQUIRED")
        self.endpoint = f"http://{parsed.netloc}/api/embed"
        self.model = embedding_model
        self.path = Path(index_path)
        if not self.path.is_absolute() or self.path.suffix.lower() != ".json":
            raise RagHold("RAG_INDEX_PATH_MUST_BE_ABSOLUTE_JSON")
        self.path = self.path.absolute()
        self._mutex = threading.RLock()
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    @contextmanager
    def _locked(self):
        with self._mutex:
            # Preserve legacy error codes for direct index/parent symlinks.
            if self.path.parent.is_symlink() or self.path.is_symlink():
                raise RagHold("RAG_INDEX_SYMLINK")
            _reject_reparse_ancestors(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _reject_reparse_ancestors(self.path)
            if self.path.parent.is_symlink() or self.path.is_symlink():
                raise RagHold("RAG_INDEX_SYMLINK")
            lock = self.path.with_name(self.path.name + ".p04lock")
            if lock.is_symlink():
                raise RagHold("RAG_LOCK_SYMLINK")
            try:
                fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise RagHold("RAG_INDEX_BUSY") from exc
            try:
                os.close(fd)
                yield
            finally:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass

    def _read(self) -> dict:
        if not self.path.exists():
            return {"schema": INDEX_SCHEMA, "model": self.model,
                    "vectorDimensions": 0, "sources": []}
        if self.path.is_symlink() or not self.path.is_file() or self.path.stat().st_size > MAX_BYTES:
            raise RagHold("RAG_INDEX_UNSAFE_OR_TOO_LARGE")
        with self.path.open("rb") as src:
            body = src.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise RagHold("RAG_INDEX_TOO_LARGE")
        try:
            data = json.loads(body)
        except (UnicodeError, ValueError) as exc:
            raise RagHold("RAG_INDEX_INVALID_JSON") from exc
        if (not isinstance(data, dict) or data.get("schema") != INDEX_SCHEMA
                or not isinstance(data.get("sources"), list)
                or type(data.get("vectorDimensions")) is not int
                or not 0 <= data["vectorDimensions"] <= MAX_DIMENSIONS):
            raise RagHold("RAG_INDEX_SCHEMA_INVALID")
        if data["sources"] and data.get("model") != self.model:
            raise RagHold("RAG_EMBEDDING_MODEL_CHANGED_REINDEX_REQUIRED")
        return data

    def _write(self, data: dict) -> None:
        import tempfile
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(prefix=".nox-rag-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "wb") as stream:
                payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if len(payload) > MAX_BYTES:
                    raise RagHold("RAG_INDEX_TOO_LARGE")
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.is_symlink():
                raise RagHold("RAG_INDEX_SYMLINK")
            os.replace(tmp, self.path)
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

    def _embeddings(self, values: list[str]) -> list[list[float]]:
        if not values:
            raise RagHold("RAG_EMPTY_EMBEDDING_REQUEST")
        result = []
        for start in range(0, len(values), 32):
            batch = values[start:start + 32]
            request = Request(self.endpoint,
                              json.dumps({"model": self.model, "input": batch,
                                          "truncate": False}).encode("utf-8"),
                              {"Content-Type": "application/json"}, method="POST")
            try:
                with self._opener.open(request, timeout=45) as response:
                    payload = response.read(MAX_EMBED_REPLY + 1)
            except RagHold:
                raise
            except Exception as exc:
                raise RagHold("LOCAL_OLLAMA_EMBED_UNAVAILABLE") from exc
            if len(payload) > MAX_EMBED_REPLY:
                raise RagHold("OLLAMA_EMBED_RESPONSE_TOO_LARGE")
            try:
                vectors = json.loads(payload)["embeddings"]
            except (KeyError, TypeError, ValueError) as exc:
                raise RagHold("OLLAMA_EMBED_RESPONSE_INVALID") from exc
            if not isinstance(vectors, list) or len(vectors) != len(batch):
                raise RagHold("OLLAMA_EMBED_BATCH_INCOMPLETE")
            for vector in vectors:
                if (not isinstance(vector, list) or not 1 <= len(vector) <= MAX_DIMENSIONS
                        or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)):
                    raise RagHold("OLLAMA_EMBED_VECTOR_INVALID")
                norm = math.sqrt(sum(x * x for x in vector))
                if not math.isfinite(norm) or norm <= 0:
                    raise RagHold("OLLAMA_EMBED_VECTOR_ZERO")
                result.append([float(x / norm) for x in vector])
        if len({len(v) for v in result}) != 1:
            raise RagHold("OLLAMA_EMBED_DIMENSIONS_CHANGED")
        return result

    def ingest_file(self, owner_sid: str, conversation_id: str, file_path: str | Path) -> dict:
        """Read authorized local UTF-8 text once; host must authorize this path first."""
        _scope(owner_sid, conversation_id)
        path = Path(file_path)
        if not path.is_absolute() or str(path).startswith(("//", "\\\\")):
            raise RagHold("RAG_LOCAL_FILE_PATH_REQUIRED")
        _safe_name(path.name)
        # Existing callers depend on the original direct-file error code.
        if path.is_symlink():
            raise RagHold("RAG_FILE_SYMLINK_BLOCKED")
        _reject_reparse_ancestors(path)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 8 * 1024 * 1024:
                raise RagHold("RAG_FILE_SIZE_OR_TYPE_INVALID")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise RagHold("RAG_FILE_TOO_LARGE")
        finally:
            os.close(fd)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RagHold("RAG_FILE_NOT_UTF8") from exc
        canonical = str(path.resolve(strict=True))
        if os.name == "nt":
            canonical = canonical.upper()
        source_id = "file:" + _sha(canonical.encode("utf-8"))
        return self.ingest_text(owner_sid, conversation_id, source_id, path.name, text,
                                _source_sha=_sha(raw))

    def ingest_text(self, owner_sid: str, conversation_id: str, source_id: str,
                    file_name: str, text: str, *, _source_sha: str | None = None) -> dict:
        _scope(owner_sid, conversation_id)
        _safe_name(file_name)
        if (not isinstance(source_id, str) or not 0 < len(source_id) <= 128
                or any(ord(c) < 32 for c in source_id)):
            raise RagHold("RAG_SOURCE_ID_INVALID")
        if (not isinstance(text, str) or not text.strip() or len(text) > MAX_SOURCE_CHARS
                or len(text.encode("utf-8")) > 8 * 1024 * 1024 or "\x00" in text):
            raise RagHold("RAG_SOURCE_TEXT_INVALID")
        identity = _sha(text.encode("utf-8")) if _source_sha is None else _source_sha
        if not SHA_RE.fullmatch(identity):
            raise RagHold("RAG_SOURCE_SHA_INVALID")
        with self._locked():
            current = self._read()
            for item in current["sources"]:
                if ((item.get("ownerSid"), item.get("conversationId"), item.get("sourceId"))
                        == (owner_sid, conversation_id, source_id)
                        and item.get("sourceIdentitySha256") == identity
                        and item.get("fileName") == file_name):
                    chunks = item.get("chunks")
                    if not isinstance(chunks, list) or not chunks:
                        raise RagHold("RAG_INDEX_CHUNKS_INVALID")
                    for entry in chunks:
                        if (not isinstance(entry, dict)
                                or not isinstance(entry.get("text"), str)
                                or _sha(entry["text"].encode("utf-8")) != entry.get("chunkSha256")
                                or not isinstance(entry.get("vector"), list)
                                or len(entry["vector"]) != current["vectorDimensions"]
                                or any(type(v) not in (float, int) or not math.isfinite(v)
                                       for v in entry["vector"])):
                            raise RagHold("RAG_INDEX_CHUNK_INTEGRITY_FAILED")
                    return {"source_id": source_id, "sha256": identity,
                            "indexed_chunks": len(chunks), "unchanged": True}
        chunks = list(_chunks(text))
        vectors = self._embeddings(chunks)
        source = {"ownerSid": owner_sid, "conversationId": conversation_id,
                  "sourceId": source_id, "fileName": file_name,
                  "sourceIdentitySha256": identity,
                  "chunks": [{"chunkIndex": i, "chunkSha256": _sha(c.encode("utf-8")),
                              "text": c, "vector": vectors[i]} for i, c in enumerate(chunks)]}
        with self._locked():
            data = self._read()
            if data["sources"] and (data["model"] != self.model
                                    or data["vectorDimensions"] != len(vectors[0])):
                raise RagHold("RAG_INDEX_REINDEX_REQUIRED")
            data["model"], data["vectorDimensions"] = self.model, len(vectors[0])
            data["sources"] = [s for s in data["sources"] if
                               (s.get("ownerSid"), s.get("conversationId"), s.get("sourceId"))
                               != (owner_sid, conversation_id, source_id)]
            data["sources"].append(source)
            self._write(data)
        return {"source_id": source_id, "sha256": source["sourceIdentitySha256"],
                "indexed_chunks": len(chunks), "unchanged": False}

    def search(self, owner_sid: str, conversation_id: str, query: str, top_k: int = 5) -> list[dict]:
        _scope(owner_sid, conversation_id)
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise RagHold("RAG_QUERY_INVALID")
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise RagHold("RAG_TOPK_INVALID")
        with self._locked():
            data = self._read()
            scoped = [s for s in data["sources"]
                      if s.get("ownerSid") == owner_sid and s.get("conversationId") == conversation_id]
        if not scoped:
            return []
        vector = self._embeddings([query])[0]
        if data["vectorDimensions"] != len(vector):
            raise RagHold("RAG_INDEX_MODEL_DIMENSIONS_CHANGED")
        hits = []
        for item in scoped:
            if not isinstance(item.get("chunks"), list) or not SHA_RE.fullmatch(str(item.get("sourceIdentitySha256", ""))):
                raise RagHold("RAG_SOURCE_PROVENANCE_INVALID")
            for chunk in item["chunks"]:
                content = chunk.get("text")
                stored = chunk.get("vector")
                if (not isinstance(content, str) or _sha(content.encode("utf-8")) != chunk.get("chunkSha256")
                        or not isinstance(stored, list) or len(stored) != len(vector)
                        or any(type(x) not in (int, float) or not math.isfinite(x) for x in stored)):
                    raise RagHold("RAG_CHUNK_PROVENANCE_INVALID")
                mag = math.sqrt(sum(x * x for x in stored))
                if mag <= 0 or not math.isfinite(mag):
                    raise RagHold("RAG_VECTOR_ZERO")
                score = sum(a * b for a, b in zip(stored, vector)) / mag
                hits.append({"source_id": item["sourceId"], "title": item["fileName"],
                             "text": content, "chunk_sha256": chunk["chunkSha256"],
                             "chunk_index": chunk["chunkIndex"], "score": score})
        hits.sort(key=lambda x: x["score"], reverse=True)
        return hits[:top_k]

    def context(self, owner_sid: str, conversation_id: str,
                query: str, top_k: int = 5) -> dict:
        hits = self.search(owner_sid, conversation_id, query, top_k)
        parts, provenance = [], []
        chars = 0
        for hit in hits:
            if (not isinstance(hit["source_id"], str) or len(hit["source_id"]) > 128
                    or not isinstance(hit["title"], str) or len(hit["title"]) > 200):
                raise RagHold("RAG_PROVENANCE_P02_INCOMPATIBLE")
            name = quote(hit["title"], safe="")
            header = f"[SOURCE: {name}#{hit['chunk_index'] + 1}; SHA256:{hit['chunk_sha256']}]\n"
            length = len(header) + len(hit["text"]) + (2 if parts else 0)
            if chars + length > MAX_CONTEXT_CHARS:
                break
            parts.append(header + hit["text"])
            chars += length
            provenance.append({"source_id": hit["source_id"], "title": hit["title"],
                               "verified": True})
        return {"context": "\n\n".join(parts), "sources": provenance}

    def delete_source(self, owner_sid: str, conversation_id: str, source_id: str) -> bool:
        _scope(owner_sid, conversation_id)
        with self._locked():
            data = self._read()
            prior = len(data["sources"])
            data["sources"] = [s for s in data["sources"] if
                               (s.get("ownerSid"), s.get("conversationId"), s.get("sourceId"))
                               != (owner_sid, conversation_id, source_id)]
            if len(data["sources"]) != prior:
                self._write(data)
                return True
            return False

    def delete_conversation(self, owner_sid: str, conversation_id: str) -> int:
        _scope(owner_sid, conversation_id)
        with self._locked():
            data = self._read()
            prior = len(data["sources"])
            data["sources"] = [s for s in data["sources"] if
                               (s.get("ownerSid"), s.get("conversationId"))
                               != (owner_sid, conversation_id)]
            removed = prior - len(data["sources"])
            if removed:
                self._write(data)
            return removed


def p02_callback(index: LocalRag, resolve_owner_sid: Callable[[str, str], str]):
    """Adapter for existing P02 ChatBridge.rag_context callback, no second chat."""
    if not callable(resolve_owner_sid):
        raise RagHold("TRUSTED_SID_RESOLVER_REQUIRED")

    def get_context(tenant: str, principal: str, chat_id: str, prompt: str) -> dict:
        # P02 validates history/ACL before calling us; #6 maps identities to SID.
        sid = resolve_owner_sid(tenant, principal)
        return index.context(sid, chat_id, prompt)
    return get_context
