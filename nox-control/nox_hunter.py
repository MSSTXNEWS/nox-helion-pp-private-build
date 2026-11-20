#!/usr/bin/env python3
"""NOX Hunter: bounded, read-only source polling with a local HTTP cache.

This is a callable source component. It does not schedule itself, write S03,
create tasks, or run arbitrary commands. An existing approved scheduler may
invoke poll_due at its own cadence after normal admission.
Supported kinds: rss, atom (including arXiv Atom feeds), github_releases,
crossref, and html_page.
"""
from __future__ import annotations

import argparse
from email.utils import parsedate_to_datetime
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

SCHEMA = "nox.hunter.sources.v1"
KINDS = {"rss", "atom", "github_releases", "crossref", "html_page"}
MIN_INTERVAL = 60
MAX_INTERVAL = 30 * 24 * 60 * 60
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
USER_AGENT = "NOX-Hunter/1.0 (+read-only source monitor)"
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class HunterError(ValueError):
    """Invalid source configuration or unsafe source URL."""


def _now() -> float:
    return time.time()


def _canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise HunterError("URL must use HTTPS and include a host")
    if parts.username or parts.password:
        raise HunterError("credentials in URLs are forbidden")
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise HunterError("local hostnames are forbidden")
    try:
        port = parts.port
    except ValueError as exc:
        raise HunterError("invalid HTTPS port") from exc
    if port not in (None, 443):
        raise HunterError("non-default HTTPS ports are forbidden")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise HunterError("non-public IP URLs are forbidden")
    path = parts.path or "/"
    query = [
        (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
    ]
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def _allowed_host(host: str, allowed_hosts: Iterable[str]) -> bool:
    return host.lower().rstrip(".") in {str(item).lower().rstrip(".") for item in allowed_hosts}


def _validate_url(value: str, allowed_hosts: Iterable[str]) -> str:
    url = _canonical_url(value)
    host = urlsplit(url).hostname or ""
    if not _allowed_host(host, allowed_hosts):
        raise HunterError("source host is not in its explicit allowed_hosts list")
    return url


def _validate_source(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HunterError("each source must be an object")
    source_id = raw.get("id")
    kind = raw.get("kind")
    allowed_hosts = raw.get("allowed_hosts")
    interval = raw.get("interval_seconds")
    if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", source_id):
        raise HunterError("source id must use 1-80 safe characters")
    if kind not in KINDS:
        raise HunterError("unsupported source kind")
    if not isinstance(allowed_hosts, list) or not allowed_hosts or any(not isinstance(h, str) or not h for h in allowed_hosts):
        raise HunterError("allowed_hosts must be a non-empty list of exact host names")
    if isinstance(interval, bool) or not isinstance(interval, int) or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise HunterError("interval_seconds must be between 60 seconds and 30 days")
    url = _validate_url(raw.get("url", ""), allowed_hosts)
    return {
        "id": source_id,
        "kind": kind,
        "url": url,
        "allowed_hosts": [h.lower().rstrip(".") for h in allowed_hosts],
        "interval_seconds": interval,
    }


def load_config(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("sources"), list):
        raise HunterError(f"config must contain schema={SCHEMA!r} and a sources array")
    sources = [_validate_source(item) for item in data["sources"]]
    ids = [source["id"] for source in sources]
    if len(ids) != len(set(ids)):
        raise HunterError("source ids must be unique")
    return sources


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: list[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _VisibleText(HTMLParser):
    _hidden = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._hidden:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._hidden and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


def _plain(value: str) -> str:
    parser = _VisibleText()
    try:
        parser.feed(value)
        parser.close()
        return " ".join(" ".join(parser.parts).split())
    except Exception:
        return " ".join(value.split())


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if _local(child.tag) in names:
            return " ".join(" ".join(child.itertext()).split())
    return ""


def _feed_items(body: bytes) -> list[dict[str, str]]:
    upper = body.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise HunterError("DTD/entity declarations are not accepted")
    root = ET.fromstring(body)
    result: list[dict[str, str]] = []
    for node in root.iter():
        if _local(node.tag) not in {"item", "entry"}:
            continue
        title = _child_text(node, {"title"})
        link = ""
        for child in list(node):
            if _local(child.tag) == "link":
                href = child.attrib.get("href", "").strip()
                rel = child.attrib.get("rel", "alternate").lower()
                text = " ".join(" ".join(child.itertext()).split())
                if href and rel in {"alternate", ""}:
                    link = href
                    break
                if not link and (href or text):
                    link = href or text
        content = _child_text(node, {"content", "encoded", "summary", "description"})
        published = _child_text(node, {"published", "updated", "pubdate", "date"})
        if title or content or link:
            result.append({"title": title, "url": link, "content": _plain(content), "published": published})
    return result


def _github_items(body: bytes) -> list[dict[str, str]]:
    decoded = json.loads(body)
    if not isinstance(decoded, list):
        raise HunterError("GitHub releases response must be a JSON array")
    items = []
    for release in decoded:
        if not isinstance(release, dict):
            continue
        title = str(release.get("name") or release.get("tag_name") or "").strip()
        url = str(release.get("html_url") or "").strip()
        content = str(release.get("body") or "").strip()
        if title or url or content:
            items.append({
                "title": title,
                "url": url,
                "content": content,
                "published": str(release.get("published_at") or release.get("created_at") or ""),
            })
    return items


def _crossref_items(body: bytes) -> list[dict[str, str]]:
    decoded = json.loads(body)
    message = decoded.get("message", {}) if isinstance(decoded, dict) else {}
    records = message.get("items", []) if isinstance(message, dict) else []
    if not isinstance(records, list):
        raise HunterError("Crossref message.items must be a JSON array")
    items = []
    for record in records:
        if not isinstance(record, dict):
            continue
        title_value = record.get("title") or []
        title = str(title_value[0] if isinstance(title_value, list) and title_value else title_value).strip()
        doi = str(record.get("DOI") or "").strip()
        url = str(record.get("URL") or (f"https://doi.org/{doi}" if doi else "")).strip()
        abstract = _plain(str(record.get("abstract") or ""))
        date = record.get("published-print") or record.get("published-online") or record.get("created") or {}
        date_parts = date.get("date-parts", [[]]) if isinstance(date, dict) else [[]]
        published = "-".join(str(part) for part in date_parts[0]) if date_parts and date_parts[0] else ""
        if title or url:
            items.append({"title": title, "url": url, "content": abstract, "published": published})
    return items


def _page_items(body: bytes, source_url: str) -> list[dict[str, str]]:
    parser = _VisibleText()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    text = " ".join(" ".join(parser.parts).split())
    return [{"title": text[:240], "url": source_url, "content": text, "published": ""}] if text else []


def _parse(source: dict[str, Any], body: bytes) -> list[dict[str, str]]:
    if source["kind"] in {"rss", "atom"}:
        return _feed_items(body)
    if source["kind"] == "github_releases":
        return _github_items(body)
    if source["kind"] == "crossref":
        return _crossref_items(body)
    return _page_items(body, source["url"])


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS http_cache (
            source_id TEXT NOT NULL,
            url TEXT NOT NULL,
            etag TEXT,
            last_modified TEXT,
            content_type TEXT,
            body BLOB NOT NULL,
            fetched_at REAL NOT NULL,
            checked_at REAL NOT NULL,
            PRIMARY KEY (source_id, url)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_state (
            source_id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            next_poll_at REAL NOT NULL,
            failures INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            source_id TEXT NOT NULL,
            item_url TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            published TEXT NOT NULL,
            first_seen_at REAL NOT NULL,
            PRIMARY KEY (source_id, item_url, content_sha256)
        )
    """)
    conn.commit()


def _fingerprint(source: dict[str, Any]) -> str:
    stable = {key: source[key] for key in ("id", "kind", "url", "allowed_hosts", "interval_seconds")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def _retry_delay(error: HTTPError | URLError, interval: int) -> int:
    retry = None
    if isinstance(error, HTTPError):
        value = error.headers.get("Retry-After") if error.headers else None
        if value:
            try:
                retry = int(value)
            except ValueError:
                try:
                    retry = int(parsedate_to_datetime(value).timestamp() - _now())
                except (TypeError, ValueError, OverflowError):
                    retry = None
    if retry is not None:
        return max(MIN_INTERVAL, min(MAX_INTERVAL, retry))
    return max(MIN_INTERVAL, min(interval, 300))


def _fetch(source: dict[str, Any], cached: sqlite3.Row | None, max_bytes: int) -> tuple[bytes, str | None, str | None, str | None, bool]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, application/xml, application/json, text/html;q=0.9, */*;q=0.1",
    }
    if cached:
        if cached["etag"]:
            headers["If-None-Match"] = cached["etag"]
        if cached["last_modified"]:
            headers["If-Modified-Since"] = cached["last_modified"]
    request = Request(source["url"], headers=headers)
    opener = build_opener(_SafeRedirect(source["allowed_hosts"]))
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise HunterError(f"response exceeds max_bytes={max_bytes}")
            return body, response.headers.get("ETag"), response.headers.get("Last-Modified"), response.headers.get("Content-Type"), False
    except HTTPError as exc:
        if exc.code == 304 and cached:
            return bytes(cached["body"]), cached["etag"], cached["last_modified"], cached["content_type"], True
        raise


def _item_record(source: dict[str, Any], item: dict[str, str], now: float) -> tuple[str, str, str, str, str, str, float]:
    title = " ".join(str(item.get("title", "")).split())
    content = " ".join(str(item.get("content", "")).split())
    raw_url = urljoin(source["url"], str(item.get("url") or source["url"]).strip())
    try:
        # Item links are stored as references only and are never fetched.
        item_url = _canonical_url(raw_url)
    except HunterError:
        item_url = source["url"]
    digest = hashlib.sha256((title + "\n" + content).encode("utf-8")).hexdigest()
    return (source["id"], item_url, digest, title, content, str(item.get("published", "")), now)


def _poll_one(conn: sqlite3.Connection, source: dict[str, Any], now: float, max_bytes: int) -> dict[str, Any]:
    fingerprint = _fingerprint(source)
    state = conn.execute("SELECT * FROM source_state WHERE source_id=?", (source["id"],)).fetchone()
    if state and state["fingerprint"] == fingerprint and state["next_poll_at"] > now:
        return {"source_id": source["id"], "status": "not_due", "added": 0, "next_poll_at": state["next_poll_at"]}
    cached = conn.execute(
        "SELECT * FROM http_cache WHERE source_id=? AND url=?",
        (source["id"], source["url"]),
    ).fetchone()
    try:
        body, etag, modified, content_type, not_modified = _fetch(source, cached, max_bytes)
        parsed = _parse(source, body)
        inserted = 0
        for item in parsed:
            record = _item_record(source, item, now)
            cursor = conn.execute(
                "INSERT OR IGNORE INTO items "
                "(source_id,item_url,content_sha256,title,content,published,first_seen_at) "
                "VALUES(?,?,?,?,?,?,?)",
                record,
            )
            inserted += cursor.rowcount
        conn.execute(
            "INSERT INTO http_cache(source_id,url,etag,last_modified,content_type,body,fetched_at,checked_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,url) DO UPDATE SET "
            "etag=excluded.etag,last_modified=excluded.last_modified,content_type=excluded.content_type,"
            "body=excluded.body,fetched_at=CASE WHEN ? THEN http_cache.fetched_at ELSE excluded.fetched_at END,"
            "checked_at=excluded.checked_at",
            (source["id"], source["url"], etag, modified, content_type, sqlite3.Binary(body), now, now, int(not_modified)),
        )
        next_poll = now + source["interval_seconds"]
        conn.execute(
            "INSERT INTO source_state(source_id,fingerprint,next_poll_at,failures,last_error) VALUES(?,?,?,0,NULL) "
            "ON CONFLICT(source_id) DO UPDATE SET fingerprint=excluded.fingerprint,"
            "next_poll_at=excluded.next_poll_at,failures=0,last_error=NULL",
            (source["id"], fingerprint, next_poll),
        )
        return {
            "source_id": source["id"],
            "status": "not_modified" if not_modified else "polled",
            "items_seen": len(parsed),
            "added": inserted,
            "next_poll_at": next_poll,
        }
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, ET.ParseError) as exc:
        failures = (state["failures"] + 1) if state and state["fingerprint"] == fingerprint else 1
        delay = _retry_delay(exc, source["interval_seconds"]) if isinstance(exc, (HTTPError, URLError)) else MIN_INTERVAL
        next_poll = now + delay
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
        conn.execute(
            "INSERT INTO source_state(source_id,fingerprint,next_poll_at,failures,last_error) VALUES(?,?,?,?,?) "
            "ON CONFLICT(source_id) DO UPDATE SET fingerprint=excluded.fingerprint,"
            "next_poll_at=excluded.next_poll_at,failures=excluded.failures,last_error=excluded.last_error",
            (source["id"], fingerprint, next_poll, failures, error),
        )
        return {"source_id": source["id"], "status": "error", "added": 0, "error": error, "next_poll_at": next_poll}


def poll_due(
    sources: list[dict[str, Any]],
    state_path: str | os.PathLike[str],
    *,
    now: float | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[dict[str, Any]]:
    """Fetch each due source once; store HTTP cache and URL+content-deduped items."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1024 <= max_bytes <= 25 * 1024 * 1024:
        raise HunterError("max_bytes must be between 1 KiB and 25 MiB")
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        stamp = _now() if now is None else now
        outcomes = [_poll_one(conn, _validate_source(source), stamp, max_bytes) for source in sources]
        conn.commit()
        return outcomes
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Poll due NOX Hunter sources once (read-only; no S03 writes).")
    parser.add_argument("--config", required=True, help="JSON source catalog using schema nox.hunter.sources.v1")
    parser.add_argument("--state", required=True, help="local SQLite cache/state path")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    try:
        sources = load_config(args.config)
        result = poll_due(sources, args.state, max_bytes=args.max_bytes)
    except (OSError, json.JSONDecodeError, HunterError) as exc:
        print(json.dumps({"status": "config_error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}), file=sys.stderr)
        return 2
    print(json.dumps({"schema": "nox.hunter.poll.v1", "results": result}, ensure_ascii=False, sort_keys=True))
    return 0 if all(item["status"] != "error" for item in result) else 1


if __name__ == "__main__":
    raise SystemExit(main())

