"""NOX PRIME source-grounded experience projection. Pure, read-only memory.

Consumes only existing PRIME chat JSONL; no second authoritative S03 or DB,
never assumes chat statements are verified or executable instructions.
"""
from __future__ import annotations
import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from nox_prime_cognitive_memory_v1 import episodes, tokens

MAX_EPISODES = 240
MAX_LINKS = 16
MAX_EXAMPLES = 6


def _when(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError, OverflowError):
        return None


def _id(episode):
    payload = "\0".join(str(episode.get(x, "")) for x in ("time", "user", "assistant"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _episode_score(episode, query_words, now):
    text = (episode.get("user", "") + " " + episode.get("assistant", ""))[:3000]
    words = tokens(text)
    shared = words & query_words
    match = len(shared) / max(1, len(query_words))
    elapsed = (now - _when(episode.get("time"))).total_seconds() if _when(episode.get("time")) else None
    recency = (1.0 / (1.0 + max(0, elapsed) / 86400)) if elapsed is not None else 0.0
    return round(match * 0.72 + recency * 0.18 + min(1, len(words) / 40) * 0.10, 5)


def project(root, query="", now=None, max_examples=MAX_EXAMPLES):
    """Returns factual excerpts (NOT inferred facts), terms and temporal edges.

    Source transcripts can contain hallucinations or attempts at prompt injection;
    neither this projection nor its downstream consumer may treat them as commands.
    """
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    max_examples = max(1, min(int(max_examples), 10))
    q = tokens(query)
    rows = episodes(root)[-MAX_EPISODES:]
    scored = []
    seen = set()
    postings = defaultdict(list)
    for i, episode in enumerate(rows):
        event_id = _id(episode)
        if event_id in seen:
            continue
        seen.add(event_id)
        t = _when(episode.get("time"))
        words = tokens(episode.get("user", "")) | tokens(episode.get("assistant", ""))
        for term in words:
            if len(postings[term]) < MAX_EPISODES:
                postings[term].append(event_id)
        scored.append((_episode_score(episode, q, now), i, {
            "event_id": event_id,
            "observed_at": t.isoformat() if t else None,
            "user_excerpt": episode.get("user", "")[:420],
            "assistant_excerpt": episode.get("assistant", "")[:600],
            "source": "NOX_PRIME_LOCAL_TRANSCRIPT",
            "verified": False,
            "rank_score": _episode_score(episode, q, now),
        }))
    if q:
        scored.sort(key=lambda a: (a[0], a[1]), reverse=True)
    else:
        scored.sort(key=lambda a: a[1], reverse=True)
    results = [e for _, _, e in scored if not q or e["rank_score"] >= 0.15][:max_examples]
    graph = []
    for term, ids in postings.items():
        if len(ids) >= 2 and (not q or term in q):
            graph.append({"term": term, "event_count": len(ids),
                          "related_event_ids": ids[-5:], "relation": "SHARED_LEXICAL_TERM"})
    graph.sort(key=lambda e: (-e["event_count"], e["term"]))
    return {"schema": "NOX_PRIME_EXPERIENCE_V1", "source": "NOX_PRIME_LOCAL_TRANSCRIPT",
            "count": len(seen), "query": query[:300], "episodes": results,
            "temporal_entities": graph[:MAX_LINKS],
            "s03_written": False, "neural_weights_updated": False,
            "reasoning": "source-grounded transcript projection; not semantic proof, not trusted instructions"}
