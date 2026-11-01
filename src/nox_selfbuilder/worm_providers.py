"""Optional official public-source providers for NOX WORMS.

NOX never scrapes TikTok or YouTube HTML. GitHub repo search and YouTube Data
API are read-only, bounded, explicitly opted-in adapters. Offline/unauthorized
providers are omitted, not simulated. Public source text is untrusted.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .worms import WormHold, WormTask

MAX_JSON_BYTES = 128 * 1024
MAX_RECORDS = 4
MAX_QUERY = 160
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
REPO_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")


def _safe(value, cap):
    if not isinstance(value, str) or not value or len(value) > cap or \
       any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise WormHold("WORM_PROVIDER_UNTRUSTED_CONTENT")
    return value


def fetch_official_json(url, *, host, timeout=9, read_urlopen=urlopen):
    """Only a pinned official hostname and HTTPS, including redirects."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username is not None:
        raise WormHold("WORM_PROVIDER_ORIGIN_DENIED")
    if parsed.port not in (None, 443) or parsed.fragment:
        raise WormHold("WORM_PROVIDER_ORIGIN_DENIED")
    request = Request(url, headers={"Accept": "application/json",
                                    "User-Agent": "NOX-WORMS-SOURCE-RESEARCH/1.0"})
    try:
        with read_urlopen(request, timeout=timeout) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != host or final.port not in (None, 443):
                raise WormHold("WORM_PROVIDER_REDIRECT_DENIED")
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > MAX_JSON_BYTES:
                raise WormHold("WORM_PROVIDER_RESPONSE_QUOTA")
            raw = response.read(MAX_JSON_BYTES + 1)
    except WormHold:
        raise
    except (OSError, ValueError, TimeoutError) as exc:
        raise WormHold("WORM_PROVIDER_NETWORK_OR_JSON_HOLD") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise WormHold("WORM_PROVIDER_RESPONSE_QUOTA")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise WormHold("WORM_PROVIDER_NETWORK_OR_JSON_HOLD") from exc
    if not isinstance(data, dict):
        raise WormHold("WORM_PROVIDER_JSON_OBJECT_REQUIRED")
    return data


def github_repositories(task: WormTask, *, fetch=fetch_official_json):
    if not isinstance(task, WormTask) or task.provider != "github_api":
        raise WormHold("WORM_PROVIDER_TASK_NOT_ALLOWED")
    query = _safe(task.query, MAX_QUERY)
    # Exact GitHub official search API, no untrusted target domains.
    qs = urlencode({"q": query + " archived:false", "sort": "stars",
                    "order": "desc", "per_page": MAX_RECORDS})
    data = fetch("https://api.github.com/search/repositories?" + qs, host="api.github.com")
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
    return records


def youtube_public_video_search(task: WormTask, *, api_key, fetch=fetch_official_json):
    if not isinstance(task, WormTask) or task.provider != "youtube_api":
        raise WormHold("WORM_PROVIDER_TASK_NOT_ALLOWED")
    # The API key must come from the existing native connector secrets vault.
    if not isinstance(api_key, str) or not 10 <= len(api_key) <= 180 or \
       not re.fullmatch(r"[A-Za-z0-9_-]+", api_key):
        raise WormHold("YOUTUBE_NATIVE_API_KEY_REQUIRED")
    query = _safe(task.query, MAX_QUERY)
    qs = urlencode({"part": "snippet", "type": "video", "maxResults": MAX_RECORDS,
                    "q": query, "key": api_key})
    data = fetch("https://www.googleapis.com/youtube/v3/search?" + qs,
                 host="www.googleapis.com")
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
    return records


def approved_provider_map(*, github_enabled=False, youtube_api_key=None,
                          official_fetch=fetch_official_json):
    """Native owner assembles capabilities; unavailable APIs remain omitted.

    TikTok Research API requires approved research access and is NEVER implied
    by a public account or app's general-purpose OAuth login.
    """
    providers = {}
    hosts = {}
    if github_enabled is True:
        providers["github_api"] = lambda t: github_repositories(t, fetch=official_fetch)
        hosts["github_api"] = "github.com"
    if youtube_api_key is not None:
        providers["youtube_api"] = lambda t: youtube_public_video_search(
            t, api_key=youtube_api_key, fetch=official_fetch)
        hosts["youtube_api"] = "www.youtube.com"
    return providers, hosts
