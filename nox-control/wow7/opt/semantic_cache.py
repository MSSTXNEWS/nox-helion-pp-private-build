#!/usr/bin/env python3
"""OPT-16 semantic_cache.py - проверяемый семантический кэш ответов NOX (stdlib + sqlite3).

Идея vCache (arXiv 2502.03771) в упрощённом виде: порог схожести ПО ЗАПИСИ, который
растёт при ошибочных попаданиях и чуть снижается при подтверждённых; часть попаданий
помечается explore=True (вызывающий всё равно зовёт LLM и сообщает feedback).
Безопасность: ключ контекста ctx_key = sha(душа, эпоха памяти S03, персона, модель) -
смена любого элемента отрезает старые ответы. Не кэшируются время-/состояние-зависимые
вопросы и усечённые/пустые ответы.
Эмбеддер: HashEmbedder (символьные n-граммы, без зависимостей) или HttpEmbedder
(/v1/embeddings llama-server, напр. bge-m3 на :8083 с --embeddings).
"""
import argparse, hashlib, json, math, random, re, sqlite3, sys, time, urllib.request

_WORD = re.compile(r"[a-zа-я0-9]+")
VOLATILE = re.compile(
    r"\b(сегодня|сейчас|вчера|завтра|тепер|текущ\w*|погод\w*|курс\w*|новост\w*|котировк\w*|"
    r"который час|сколько времени|как (ты )?себя чувству\w*|настроени\w*|как дела|"
    r"что (ты )?(думаешь|чувствуешь)|today|now|weather|news)\b")


def normalize(text):
    t = text.lower().replace("ё", "е")
    return " ".join(_WORD.findall(t))


class HashEmbedder:
    """Разреженный вектор из хэшей символьных 3-5-грамм слов; косинус."""
    name = "hash-ngram-v1"

    def __init__(self, dim=2048):
        self.dim = dim

    def embed(self, text):
        t = " " + normalize(text) + " "
        vec = {}
        for n in (3, 4, 5):
            for i in range(len(t) - n + 1):
                h = int.from_bytes(hashlib.blake2b(t[i:i + n].encode(), digest_size=4).digest(), "big") % self.dim
                vec[h] = vec.get(h, 0.0) + 1.0
        return _unit(vec)


class HttpEmbedder:
    """OpenAI-совместимый /v1/embeddings (llama-server --embeddings)."""

    def __init__(self, url, model="", timeout=10.0):
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
        self.name = "http:" + (model or url)

    def embed(self, text):
        body = json.dumps({"input": text, "model": self.model}).encode()
        req = urllib.request.Request(self.url + "/v1/embeddings", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        v = data["data"][0]["embedding"]
        return _unit({i: float(x) for i, x in enumerate(v) if x})


def _unit(vec):
    n = math.sqrt(sum(x * x for x in vec.values())) or 1.0
    return {k: x / n for k, x in vec.items()}


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())


def make_ctx_key(soul_hash, memory_epoch, persona="", model=""):
    return hashlib.sha256("|".join([soul_hash, str(memory_epoch), persona, model]).encode()).hexdigest()[:24]


def is_cacheable(query, answer, truncated=False):
    if truncated or not answer or len(answer.strip()) < 2:
        return False, "empty_or_truncated"
    if len(normalize(query).split()) < 3:
        return False, "query_too_short"
    if VOLATILE.search(query.lower()):
        return False, "volatile_query"
    if re.search(r"(ошибка|error|traceback|не могу ответить|таймаут)", answer.lower()[:200]):
        return False, "error_like_answer"
    return True, "ok"


class Hit:
    def __init__(self, entry_id, answer, sim, exact, explore):
        self.entry_id, self.answer, self.sim, self.exact, self.explore = entry_id, answer, sim, exact, explore

    def __repr__(self):
        return f"Hit(id={self.entry_id}, sim={self.sim:.3f}, exact={self.exact}, explore={self.explore})"


class SemanticCache:
    def __init__(self, path=":memory:", embedder=None, base_thr=0.93, floor_thr=0.88,
                 explore_p=0.1, max_bad=3, clock=time.time, rng=None):
        self.db = sqlite3.connect(path)
        self.emb = embedder or HashEmbedder()
        self.base_thr, self.floor_thr, self.explore_p, self.max_bad = base_thr, floor_thr, explore_p, max_bad
        self.clock, self.rng = clock, rng or random.Random()
        self.db.execute("""CREATE TABLE IF NOT EXISTS e(id INTEGER PRIMARY KEY, ctx TEXT, qhash TEXT, q TEXT,
            vec TEXT, answer TEXT, created REAL, ttl REAL, hits INTEGER DEFAULT 0, good INTEGER DEFAULT 0,
            bad INTEGER DEFAULT 0, thr REAL, off INTEGER DEFAULT 0, emb TEXT)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix ON e(ctx, qhash)")
        self.db.commit()

    @staticmethod
    def _qh(q):
        return hashlib.sha256(normalize(q).encode()).hexdigest()

    def put(self, query, answer, ctx_key, ttl=86400.0, truncated=False):
        ok, why = is_cacheable(query, answer, truncated)
        if not ok:
            return None, why
        qh = self._qh(query)
        self.db.execute("DELETE FROM e WHERE ctx=? AND qhash=?", (ctx_key, qh))
        vec = self.emb.embed(query)
        cur = self.db.execute(
            "INSERT INTO e(ctx,qhash,q,vec,answer,created,ttl,thr,emb) VALUES(?,?,?,?,?,?,?,?,?)",
            (ctx_key, qh, query, json.dumps({str(k): v for k, v in vec.items()}), answer,
             self.clock(), ttl, self.base_thr, self.emb.name))
        self.db.commit()
        return cur.lastrowid, "ok"

    def get(self, query, ctx_key):
        if VOLATILE.search(query.lower()):
            return None
        now = self.clock()
        rows = self.db.execute("SELECT id,qhash,vec,answer,created,ttl,thr FROM e WHERE ctx=? AND off=0 AND emb=?",
                               (ctx_key, self.emb.name)).fetchall()
        rows = [r for r in rows if now - r[4] <= r[5]]
        if not rows:
            return None
        qh = self._qh(query)
        for r in rows:
            if r[1] == qh:
                return self._hit(r, 1.0, True)
        qv = self.emb.embed(query)
        best, bs = None, -1.0
        for r in rows:
            s = cosine(qv, {int(k): v for k, v in json.loads(r[2]).items()})
            if s > bs:
                best, bs = r, s
        if best is not None and bs >= best[6]:
            return self._hit(best, bs, False)
        return None

    def _hit(self, r, sim, exact):
        self.db.execute("UPDATE e SET hits=hits+1 WHERE id=?", (r[0],))
        self.db.commit()
        explore = (not exact) and self.rng.random() < self.explore_p
        return Hit(r[0], r[3], sim, exact, explore)

    def feedback(self, entry_id, sim, ok):
        """ok=False: хозяин нажал «перегенерировать»/свежий ответ не согласен -> порог выше sim."""
        row = self.db.execute("SELECT thr,bad,good FROM e WHERE id=?", (entry_id,)).fetchone()
        if not row:
            return False
        thr, bad, good = row
        if ok:
            thr, good = max(self.floor_thr, thr - 0.005), good + 1
        else:
            thr, bad = min(0.999, max(thr, sim + 0.01)), bad + 1
        off = 1 if bad >= self.max_bad else 0
        self.db.execute("UPDATE e SET thr=?,bad=?,good=?,off=? WHERE id=?", (thr, bad, good, off, entry_id))
        self.db.commit()
        return True

    def agreed(self, cached, fresh, min_sim=0.6):
        return cosine(self.emb.embed(cached), self.emb.embed(fresh)) >= min_sim

    def purge(self, ctx_key=None):
        now = self.clock()
        if ctx_key:
            n = self.db.execute("DELETE FROM e WHERE ctx=?", (ctx_key,)).rowcount
        else:
            n = self.db.execute("DELETE FROM e WHERE created+ttl<?", (now,)).rowcount
        self.db.commit()
        return n

    def stats(self):
        r = self.db.execute("SELECT COUNT(*),COALESCE(SUM(hits),0),COALESCE(SUM(good),0),COALESCE(SUM(bad),0),"
                            "COALESCE(SUM(off),0) FROM e").fetchone()
        return dict(entries=r[0], hits=r[1], good=r[2], bad=r[3], disabled=r[4])


def main(argv=None):
    ap = argparse.ArgumentParser(description="semantic cache CLI")
    ap.add_argument("--db", default="/root/nox/state/semantic_cache.sqlite")
    ap.add_argument("--embed-url", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    g = sub.add_parser("get"); g.add_argument("query"); g.add_argument("--ctx", required=True)
    p = sub.add_parser("put"); p.add_argument("query"); p.add_argument("answer"); p.add_argument("--ctx", required=True)
    sub.add_parser("purge")
    a = ap.parse_args(argv)
    c = SemanticCache(a.db, HttpEmbedder(a.embed_url) if a.embed_url else None)
    if a.cmd == "stats":
        print(json.dumps(c.stats(), ensure_ascii=False))
    elif a.cmd == "get":
        print(repr(c.get(a.query, a.ctx)))
    elif a.cmd == "put":
        print(c.put(a.query, a.answer, a.ctx))
    else:
        print(c.purge())
    return 0


if __name__ == "__main__":
    sys.exit(main())
