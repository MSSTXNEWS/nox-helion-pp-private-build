"""memory_search: быстрый поиск по памяти S03.

1) Полнотекстовый: SQLite FTS5 (если нет - запасной LIKE). Русская морфология грубая:
   запрос режется до основы (префикса), совпадение по префиксу слова.
2) Векторный (необязательно): bge-m3 через HTTP-эмбеддер, URL в env NOX_EMBED_URL.
   Если URL не задан или эмбеддер недоступен - честно работает только FTS (в ответе mode и warnings).
3) Реранкер: совпадение слов запроса, свежесть, уверенность (лестница Riverse), векторная близость.
"""
import array
import hashlib
import json
import math
import os
import re
import time
import urllib.request

from .s03_store import ref_of

DAY = 86400.0
WEIGHTS = {"match": 0.45, "vector": 0.20, "recency": 0.15, "confidence": 0.20}
RECENCY_HALF_LIFE_DAYS = 120.0
_STOP = set("и в во не на с со как что это а но или то за по из к у о об от для же бы ли ты я мы вы он она они".split())


def stem(w):
    w = w.casefold()
    return w if len(w) <= 4 else w[:max(4, min(len(w) - 2, 6))]


def query_stems(q):
    out = []
    for w in re.findall(r"\w+", q or "", re.U):
        if len(w) < 2 or w.casefold() in _STOP:
            continue
        s = stem(w)
        if s not in out:
            out.append(s)
    return out[:12]


def overlap(stems, text):
    words = [w.casefold() for w in re.findall(r"\w+", text or "", re.U)]
    if not stems:
        return 0.0
    return sum(1 for s in stems if any(w.startswith(s) for w in words)) / len(stems)


class HttpEmbedder:
    """Клиент эмбеддингов. Форматы: OpenAI-совместимый (/v1/embeddings: {"model","input"}) и TEI (/embed: {"inputs"})."""

    def __init__(self, url, model="bge-m3", timeout=10.0, batch=16, api_key=None):
        self.url, self.model, self.timeout, self.batch, self.api_key = url, model, timeout, batch, api_key

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        url = (env.get("NOX_EMBED_URL") or "").strip()
        if not url:
            return None
        return cls(url, env.get("NOX_EMBED_MODEL", "bge-m3"), float(env.get("NOX_EMBED_TIMEOUT", "10")),
                   api_key=env.get("NOX_EMBED_KEY") or None)

    def _post(self, texts):
        tei = self.url.rstrip("/").endswith("/embed")
        body = {"inputs": texts} if tei else {"model": self.model, "input": texts}
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.url, json.dumps(body).encode(), h, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if isinstance(data, dict) and "data" in data:
            vecs = [d["embedding"] for d in sorted(data["data"], key=lambda d: d.get("index", 0))]
        elif isinstance(data, dict) and "embeddings" in data:
            vecs = data["embeddings"]
        elif isinstance(data, list):
            vecs = data
        else:
            raise ValueError("неизвестный формат ответа эмбеддера")
        if len(vecs) != len(texts):
            raise ValueError("эмбеддер вернул %d векторов на %d текстов" % (len(vecs), len(texts)))
        return vecs

    def embed(self, texts):
        out = []
        for i in range(0, len(texts), self.batch):
            out.extend(self._post(texts[i:i + self.batch]))
        return out


def _cos(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


class MemorySearch:
    def __init__(self, store, embedder=None, use_env_embedder=True):
        self.s = store
        self.embedder = embedder if embedder is not None else (HttpEmbedder.from_env() if use_env_embedder else None)
        self.model_name = getattr(self.embedder, "model", "custom")

    # --- содержимое для индекса ---
    def _all_items(self):
        s = self.s
        for (i,) in s.db.execute("SELECT id FROM mem_facts WHERE status='active'"):
            yield ref_of("fact", i)
        for (i,) in s.db.execute("SELECT id FROM mem_episodes WHERE status='active'"):
            yield ref_of("episode", i)
        for (k,) in s.db.execute("SELECT key FROM mem_profile WHERE status='active'"):
            yield ref_of("profile", k)

    # --- векторный индекс ---
    def index_vectors(self, limit=500):
        """Посчитать эмбеддинги для записей без вектора/с изменившимся текстом. -> (число, предупреждение|None)."""
        if self.embedder is None:
            return 0, "эмбеддер не задан (NOX_EMBED_URL)"
        todo = []
        for ref in self._all_items():
            rec = self.s.get(ref)
            text = self.s.text_of(rec)
            tk = hashlib.sha1(text.encode()).hexdigest()[:16]
            r = self.s.db.execute("SELECT text_key, model FROM mem_vectors WHERE ref=?", (ref,)).fetchone()
            if not r or r[0] != tk or r[1] != self.model_name:
                todo.append((ref, text, tk))
            if len(todo) >= limit:
                break
        if not todo:
            return 0, None
        try:
            vecs = self.embedder.embed([t[1] for t in todo])
        except Exception as e:
            return 0, "эмбеддер недоступен: %s" % e
        for (ref, _, tk), v in zip(todo, vecs):
            self.s.db.execute("INSERT OR REPLACE INTO mem_vectors(ref,model,dim,vec,text_key) VALUES(?,?,?,?,?)",
                              (ref, self.model_name, len(v), array.array("f", v).tobytes(), tk))
        self.s.db.commit()
        return len(todo), None

    def _vector_candidates(self, query, n=50):
        qv = self.embedder.embed([query])[0]
        res = []
        for ref, dim, blob in self.s.db.execute("SELECT ref,dim,vec FROM mem_vectors WHERE model=?", (self.model_name,)):
            if dim != len(qv):
                continue
            a = array.array("f"); a.frombytes(blob)
            res.append((ref, _cos(qv, a)))
        res.sort(key=lambda x: -x[1])
        return res[:n]

    # --- текстовые кандидаты ---
    def _fts_candidates(self, stems, n=60):
        q = " OR ".join('"%s"*' % s.replace('"', "") for s in stems)
        rows = self.s.db.execute("SELECT ref FROM mem_fts WHERE mem_fts MATCH ? ORDER BY rank LIMIT ?", (q, n)).fetchall()
        return [r[0] for r in rows]

    def _like_candidates(self, stems, n=60):
        s, found = self.s, {}
        pats = ["%" + x.replace("%", "").replace("_", "") + "%" for x in stems]
        specs = [("SELECT id,text FROM mem_facts WHERE status='active' AND (%s)", "fact", "text"),
                 ("SELECT id,text||' '||COALESCE(summary,'') FROM mem_episodes WHERE status='active' AND (%s)", "episode", "text||' '||COALESCE(summary,'')"),
                 ("SELECT key,key||': '||value FROM mem_profile WHERE status='active' AND (%s)", "profile", "key||': '||value")]
        for sql, kind, expr in specs:
            cond = " OR ".join("%s LIKE ? COLLATE NOCASE" % expr for _ in pats)
            for i, _t in s.db.execute(sql % cond, pats):
                found[ref_of(kind, i)] = 1
        return list(found)[:n * 3]

    def search(self, query, k=8, kinds=None, now=None):
        """-> {"mode","hits":[{ref,type,text,score,parts,level,level_name}],"warnings":[]}"""
        now = now or time.time()
        stems = query_stems(query)
        warnings, mode = [], "fts" if self.s.fts else "like"
        cand = {}
        if stems:
            try:
                refs = self._fts_candidates(stems) if self.s.fts else self._like_candidates(stems)
            except Exception as e:     # неверный синтаксис/сбой FTS -> LIKE
                warnings.append("FTS не сработал (%s), использован LIKE" % e)
                mode, refs = "like", self._like_candidates(stems)
            for ref in refs:
                cand.setdefault(ref, 0.0)
        vec_used = False
        if self.embedder is not None and (query or "").strip():
            try:
                for ref, sim in self._vector_candidates(query):
                    if sim > 0:
                        cand[ref] = max(cand.get(ref, 0.0), sim)
                vec_used = True
                mode += "+vector"
            except Exception as e:
                warnings.append("вектор недоступен, только текстовый поиск: %s" % e)
        elif self.embedder is None:
            warnings.append("векторный поиск выключен (NOX_EMBED_URL не задан): работает только %s" % mode.upper())
        hits = []
        for ref, sim in cand.items():
            rec = self.s.get(ref)
            if rec is None or rec.get("status", "active") != "active":
                continue
            if kinds and rec["type"] not in kinds:
                continue
            text = self.s.text_of(rec)
            parts = self._parts(rec, text, stems, sim if vec_used else None, now)
            w = dict(WEIGHTS)
            if not vec_used:
                w["match"] += w.pop("vector")
                parts.pop("vector", None)
            score = sum(w[k] * parts[k] for k in w)
            hits.append({"ref": ref, "type": rec["type"], "text": text, "score": round(score, 4),
                         "parts": {a: round(b, 3) for a, b in parts.items()},
                         "level": rec.get("level"), "level_name": rec.get("level_name")})
        hits.sort(key=lambda h: (-h["score"], h["ref"]))
        return {"mode": mode, "query": query, "hits": hits[:k], "warnings": warnings}

    def _parts(self, rec, text, stems, sim, now):
        t = rec["type"]
        if t == "fact":
            age = max(0.0, now - max(rec["updated"] or 0, rec["last_access"] or 0)) / DAY
            conf = min(1.0, rec["level"] / 3.0 + (0.2 if rec["pinned"] else 0.0))
        elif t == "episode":
            age = max(0.0, now - (rec["ts"] or now)) / DAY
            conf = 0.3
        else:
            age, conf = 0.0, 0.8
        parts = {"match": overlap(stems, text), "recency": 0.5 ** (age / RECENCY_HALF_LIFE_DAYS), "confidence": conf}
        if sim is not None:
            parts["vector"] = max(0.0, min(1.0, sim))
        return parts
