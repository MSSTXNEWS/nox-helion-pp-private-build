"""PER-06: конвейер взглядов - кандидат -> 2 независимых запроса (источники) -> ОТДЕЛЬНЫЙ запрос на опровержение -> record_refutation_search.
Поиск - SearXNG (searxng_search) только на хосты из allowlist; текст результатов - данные (ищем маркеры, не исполняем). Лимит запросов в сутки."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json

import statefile
import datafence
import os
import re
import time
import urllib.parse
import urllib.request

import perpath  # noqa: F401

PRIMARY_DOMAINS = ("arxiv.org", "github.com", "docs.python.org", "developer.mozilla.org", "huggingface.co", "nature.com", "science.org",
                   "ietf.org", "w3.org", "kernel.org", "postgresql.org", "sqlite.org", "llama.cpp")
COUNTER_RX = re.compile(r"опроверг|ошибочн|миф\b|не подтвержд|неверн|заблужден|refut|debunk|incorrect|myth|fails? to replicate|retract", re.I)
ALLOW_HOSTS = ("127.0.0.1", "localhost", "::1")


def domain(url):
    h = urllib.parse.urlparse(url).hostname or ""
    return h[4:] if h.startswith("www.") else h


def kind_of(dom):
    return "primary" if any(dom == d or dom.endswith("." + d) or dom.startswith("docs.") for d in PRIMARY_DOMAINS) else "secondary"


def searxng_search(base="http://127.0.0.1:8888", allow=ALLOW_HOSTS, timeout=20, limit=8):
    host = urllib.parse.urlparse(base).hostname
    if host not in allow:
        raise PermissionError("хост поиска вне allowlist: %s" % host)

    def search(q):
        url = base.rstrip("/") + "/search?" + urllib.parse.urlencode({"q": q, "format": "json"})
        with urllib.request.urlopen(url, timeout=timeout) as r:
            res = json.loads(r.read()).get("results", [])
        return [{"url": x.get("url", ""), "title": x.get("title", ""), "snippet": x.get("content", "")} for x in res[:limit]]
    return search


class Budget:
    def __init__(self, path, per_day=60, clock=time.time):
        self.path, self.per_day, self.clock = path, per_day, clock

    def _day(self):
        return int(self.clock() // 86400)

    def used(self):
        try:
            d = json.load(open(self.path, encoding="utf-8"))
            return d["n"] if d["day"] == self._day() else 0
        except (OSError, ValueError, KeyError):
            return 0

    def take(self, k=1):
        n = self.used()
        if n + k > self.per_day:
            return False
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        statefile.save(self.path, {"day": self._day(), "n": n + k})
        return True


def hunt(beliefs, candidates, search, budget=None):
    """candidates: [(text, topic)]. -> [{id, status, need, queries, sources, refutation}]. Не доверяет модельным источникам: kind только по домену."""
    out = []
    for text, topic in candidates:
        bid = beliefs.propose(text, topic)
        if beliefs.items[bid]["status"] == "rejected_l0":
            out.append({"id": bid, "status": "rejected_l0", "need": [], "queries": 0})
            continue
        queries, srcs = 0, {}
        for q in (text, "%s %s подтверждение данные" % (topic, text)):
            if budget and not budget.take():
                break
            queries += 1
            for r in search(q):
                d = domain(r["url"])
                if d and d not in srcs and len(srcs) < 2 + (1 if queries == 1 else 0):
                    srcs[d] = r
        for d, r in srcs.items():
            beliefs.add_source(bid, d, kind_of(d), "support", r["url"][:150])
        refut = {"searched": False, "found": False}
        if budget is None or budget.take():
            q = "%s опровержение ошибка counterexample" % text
            counter = None
            for r in search(q):
                d = domain(r["url"])
                if d and d not in srcs and COUNTER_RX.search(r["title"] + " " + r["snippet"]):
                    counter = {"key": d, "kind": kind_of(d), "note": r["url"][:150]}
                    break
            beliefs.record_refutation_search(bid, q, counter)
            refut = {"searched": True, "found": bool(counter)}
            queries += 1
        out.append({"id": bid, "status": beliefs.items[bid]["status"], "need": beliefs.need(bid), "queries": queries,
                    "sources": sorted(srcs), "refutation": refut,
                    "framed": [datafence.data_frame((r.get("title", "") + ". " + r.get("snippet", "")), d, trust="низкое", limit=400)
                               for d, r in srcs.items()]})       # результаты поиска в промпт - только в рамке данных
    return out
