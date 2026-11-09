"""Optional official public-source providers for NOX WORMS.

NOX never scrapes TikTok or YouTube HTML. GitHub repo search and YouTube Data
API are read-only, bounded, explicitly opted-in adapters. Offline/unauthorized
providers are omitted, not simulated. Public source text is untrusted.
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .worms import WormHold, WormTask

MAX_JSON_BYTES = 128 * 1024
MAX_FEED_BYTES = 128 * 1024
MAX_RECORDS = 4
MAX_QUERY = 160
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
REPO_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")


def _safe(value, cap):
    if not isinstance(value, str) or not value or len(value) > cap or \
       any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise WormHold("WORM_PROVIDER_UNTRUSTED_CONTENT")
    return value


class _NoRedirect(HTTPRedirectHandler):
    """Do not contact a redirect target before validating its origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WormHold("WORM_PROVIDER_REDIRECT_DENIED")


def _strict_urlopen(request, *, timeout):
    # urllib.urlopen follows redirects before response.geturl() can inspect
    # them. Prohibit all redirects: the owner must reapprove a new feed URL.
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _approved_url(url, host):
    if (type(host) is not str or not re.fullmatch(r"[a-z0-9.-]{4,120}", host)
            or host.startswith(".") or host.endswith(".") or ".." in host
            or host == "localhost" or host.endswith((".localhost", ".local", ".internal"))):
        raise WormHold("WORM_PROVIDER_ORIGIN_DENIED")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise WormHold("WORM_PROVIDER_ORIGIN_DENIED")
    parsed = urlparse(url)
    if (type(url) is not str or len(url) > 2048 or parsed.scheme != "https"
            or parsed.hostname != host or parsed.netloc != host
            or parsed.port is not None or parsed.fragment):
        raise WormHold("WORM_PROVIDER_ORIGIN_DENIED")
    return parsed


def _read_pinned(url, *, host, accept, limit, timeout, read_urlopen=None):
    _approved_url(url, host)
    if type(timeout) not in (int, float) or not 0 < timeout <= 9:
        raise WormHold("WORM_PROVIDER_TIMEOUT_INVALID")
    request = Request(url, headers={"Accept": accept,
                                    "User-Agent": "NOX-WORMS-SOURCE-RESEARCH/1.0"})
    try:
        transport = _strict_urlopen if read_urlopen is None else read_urlopen
        with transport(request, timeout=timeout) as response:
            # This post-check also protects injected transport test doubles;
            # real default network transport never follows redirects at all.
            if response.geturl() != url:
                raise WormHold("WORM_PROVIDER_REDIRECT_DENIED")
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > limit:
                raise WormHold("WORM_PROVIDER_RESPONSE_QUOTA")
            raw = response.read(limit + 1)
    except WormHold:
        raise
    except (OSError, ValueError, TimeoutError) as exc:
        raise WormHold("WORM_PROVIDER_NETWORK_OR_JSON_HOLD") from exc
    if len(raw) > limit:
        raise WormHold("WORM_PROVIDER_RESPONSE_QUOTA")
    return raw


def fetch_official_json(url, *, host, timeout=9, read_urlopen=None):
    """Exact official endpoint. No automatic cross-origin redirect requests."""
    raw = _read_pinned(url, host=host, accept="application/json",
                       limit=MAX_JSON_BYTES, timeout=timeout,
                       read_urlopen=read_urlopen)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise WormHold("WORM_PROVIDER_NETWORK_OR_JSON_HOLD") from exc
    if not isinstance(data, dict):
        raise WormHold("WORM_PROVIDER_JSON_OBJECT_REQUIRED")
    return data


def _check_native_stop(stop):
    """Fail closed on an untrusted or unavailable native STOP indication.

    The actual native epoch remains owned by OneHost/WormSwarm; an adapter
    never resets it or assumes a failed cancellation probe means CONTINUE.
    """
    if stop is None:
        return
    if not callable(stop):
        raise WormHold("WORM_NATIVE_STOP_REQUIRED")
    try:
        revoked = stop()
    except Exception as exc:
        raise WormHold("WORM_NATIVE_STOP_UNAVAILABLE") from exc
    if type(revoked) is not bool or revoked:
        raise WormHold("WORM_NATIVE_STOP_REVOKED")


def github_repositories(task: WormTask, *, fetch=fetch_official_json, stop=None):
    if not isinstance(task, WormTask) or task.provider != "github_api":
        raise WormHold("WORM_PROVIDER_TASK_NOT_ALLOWED")
    _check_native_stop(stop)
    query = _safe(task.query, MAX_QUERY)
    # Exact GitHub official search API, no untrusted target domains.
    qs = urlencode({"q": query + " archived:false", "sort": "stars",
                    "order": "desc", "per_page": MAX_RECORDS})
    data = fetch("https://api.github.com/search/repositories?" + qs, host="api.github.com")
    _check_native_stop(stop)  # Late native STOP must not produce accepted findings.
    rows = data.get("items")
    if not isinstance(rows, list):
        raise WormHold("WORM_PROVIDER_REPO_RESULT_INVALID")
    records = []
    for row in rows[:MAX_RECORDS]:
        if not isinstance(row, dict) or not REPO_URL.fullmatch(str(row.get("html_url", ""))):
            continue
        if row.get("archived") is True:
            continue
        title = row.get("full_name")
        description = row.get("description")
        if not isinstance(description, str) or not description.strip():
            continue
        stars = row.get("stargazers_count")
        if type(stars) is not int or stars < 0:
            stars = "unverified"
        records.append({
            "url": row["html_url"], "title": _safe(title, 300),
            "excerpt": _safe(description[:900], 1200) + f" | GitHub stars: {stars}",
            "source_id": "github:" + _safe(title, 140),
            # GitHub's license field can be missing/misleading; read LICENSE
            # at the exact revision before any code is approved or executed.
            "license": "REVIEW_REQUIRED",
        })
    _check_native_stop(stop)  # Reject native revocation during result formatting.
    return records


def youtube_public_video_search(task: WormTask, *, api_key, fetch=fetch_official_json,
                                stop=None):
    if not isinstance(task, WormTask) or task.provider != "youtube_api":
        raise WormHold("WORM_PROVIDER_TASK_NOT_ALLOWED")
    _check_native_stop(stop)
    # The API key must come from the existing native connector secrets vault.
    if not isinstance(api_key, str) or not 10 <= len(api_key) <= 180 or \
       not re.fullmatch(r"[A-Za-z0-9_-]+", api_key):
        raise WormHold("YOUTUBE_NATIVE_API_KEY_REQUIRED")
    query = _safe(task.query, MAX_QUERY)
    qs = urlencode({"part": "snippet", "type": "video", "maxResults": MAX_RECORDS,
                    "q": query, "key": api_key})
    data = fetch("https://www.googleapis.com/youtube/v3/search?" + qs,
                 host="www.googleapis.com")
    _check_native_stop(stop)
    rows = data.get("items")
    if not isinstance(rows, list):
        raise WormHold("YOUTUBE_OFFICIAL_RESPONSE_REQUIRED")
    records = []
    for row in rows[:MAX_RECORDS]:
        if not isinstance(row, dict):
            continue
        vid = row.get("id", {}).get("videoId") if isinstance(row.get("id"), dict) else None
        snip = row.get("snippet")
        if not isinstance(vid, str) or not YOUTUBE_ID.fullmatch(vid) or not isinstance(snip, dict):
            continue
        title = snip.get("title")
        description = snip.get("description")
        published = snip.get("publishedAt")
        if not isinstance(title, str) or not isinstance(description, str) or not description:
            continue
        rec = {"url": "https://www.youtube.com/watch?v=" + vid,
               "title": _safe(title[:300], 300),
               "excerpt": _safe(description[:900], 1200),
               "source_id": "youtube:" + vid, "license": "REVIEW_REQUIRED"}
        if isinstance(published, str) and 0 < len(published) <= 50:
            rec["published"] = _safe(published, 50)
        records.append(rec)
    _check_native_stop(stop)  # Reject native revocation during result formatting.
    return records


def fetch_official_feed(url, *, host, timeout=9, read_urlopen=None):
    """Fetch owner-pinned RSS/Atom XML, limited bytes, no DTD or redirects."""
    raw = _read_pinned(url, host=host, accept="application/rss+xml, application/atom+xml, application/xml",
                       limit=MAX_FEED_BYTES, timeout=timeout,
                       read_urlopen=read_urlopen)
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw, flags=re.I):
        raise WormHold("WORM_FEED_DTD_DENIED")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise WormHold("WORM_FEED_XML_INVALID") from exc


def _feed_text(element, cap):
    if element is None:
        return None
    value = " ".join(element.itertext())
    if "<script" in value.lower():
        raise WormHold("WORM_PROVIDER_UNTRUSTED_CONTENT")
    # RSS descriptions often contain escaped markup: treat as plain text only.
    value = html.unescape(value)
    value = re.sub(r"<[^>]*>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None
    return _safe(value[:cap], cap)


def official_feed(task: WormTask, *, feed_url, source_host, fetch=fetch_official_feed,
                  stop=None):
    """One explicitly admitted official feed; findings are citations, not imports.

    The native owner pins feed_url AND source_host. Distinct feed/article hosts
    are allowed only when source_host is also owner-approved; arbitrary article
    links are dropped. WormSwarm supplies the quota, native read ACL and S03 ACK.
    """
    if not isinstance(task, WormTask) or task.provider != "approved_feeds":
        raise WormHold("WORM_PROVIDER_TASK_NOT_ALLOWED")
    _check_native_stop(stop)
    if type(feed_url) is not str:
        raise WormHold("WORM_PROVIDER_ORIGIN_DENIED")
    feed_host = urlparse(feed_url).hostname
    _approved_url(feed_url, feed_host)
    _approved_url("https://" + source_host + "/", source_host)
    root = fetch(feed_url, host=feed_host)
    _check_native_stop(stop)
    ATOM = "{http://www.w3.org/2005/Atom}"
    if root.tag == "rss":
        rows = root.findall("./channel/item")
        def unpack(item):
            return (item.findtext("link"), _feed_text(item.find("title"), 300),
                    _feed_text(item.find("description"), 900),
                    _feed_text(item.find("pubDate"), 50))
    elif root.tag == ATOM + "feed":
        rows = root.findall(ATOM + "entry")
        def unpack(item):
            links = item.findall(ATOM + "link")
            url = next((x.get("href") for x in links
                        if x.get("rel", "alternate") == "alternate"
                        and x.get("href")), None)
            summary = item.find(ATOM + "summary")
            if summary is None:
                summary = item.find(ATOM + "content")
            return (url, _feed_text(item.find(ATOM + "title"), 300),
                    _feed_text(summary, 900),
                    _feed_text(item.find(ATOM + "updated"), 50))
    else:
        raise WormHold("WORM_FEED_FORMAT_DENIED")
    out = []
    for row in rows[:MAX_RECORDS]:
        _check_native_stop(stop)
        url, title, excerpt, published = unpack(row)
        try:
            _approved_url(url, source_host)
        except (WormHold, ValueError, TypeError):
            continue  # no forged or unapproved source citation
        if not title or not excerpt:
            continue
        item = {"url": url, "title": title, "excerpt": excerpt,
                "source_id": "rss:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32],
                "license": "REVIEW_REQUIRED"}
        if published:
            item["published"] = published
        out.append(item)
    _check_native_stop(stop)  # Reject native revocation during result formatting.
    return out


def approved_provider_map(*, github_enabled=False, youtube_api_key=None,
                          official_fetch=fetch_official_json, approved_feed_url=None,
                          approved_source_host=None, feed_fetch=fetch_official_feed,
                          native_stop=None):
    """Native owner assembles capabilities; unavailable APIs remain omitted.

    TikTok Research API requires approved research access and is NEVER implied
    by a public account or app's general-purpose OAuth login.
    """
    # Every enabled network provider must be bound to the live native STOP.
    # A missing callback must never authorize a remote fetch.
    if (github_enabled is True or youtube_api_key is not None or
            approved_feed_url is not None) and not callable(native_stop):
        raise WormHold("WORM_NATIVE_STOP_REQUIRED")
    providers = {}
    hosts = {}
    if github_enabled is True:
        providers["github_api"] = lambda t: github_repositories(
            t, fetch=official_fetch, stop=native_stop)
        hosts["github_api"] = "github.com"
    if youtube_api_key is not None:
        providers["youtube_api"] = lambda t: youtube_public_video_search(
            t, api_key=youtube_api_key, fetch=official_fetch, stop=native_stop)
        hosts["youtube_api"] = "www.youtube.com"
    if approved_feed_url is not None:
        if native_stop is not None and not callable(native_stop):
            raise WormHold("WORM_NATIVE_STOP_REQUIRED")
        if type(approved_feed_url) is not str:
            raise WormHold("WORM_PROVIDER_ORIGIN_DENIED")
        feed_host = urlparse(approved_feed_url).hostname
        _approved_url(approved_feed_url, feed_host)
        citation_host = approved_source_host or feed_host
        _approved_url("https://" + citation_host + "/", citation_host)
        providers["approved_feeds"] = lambda t: official_feed(
            t, feed_url=approved_feed_url, source_host=citation_host,
            fetch=feed_fetch, stop=native_stop)
        hosts["approved_feeds"] = citation_host
    return providers, hosts
