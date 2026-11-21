#!/usr/bin/env python3
"""L1 RAG stub: index coordination/*.md; bge-m3 (port 8082) with safe BM25 fallback. stdlib only.

  rag_stub.py index [--root DIR] [--out FILE]
  rag_stub.py query "text" [--out FILE] [-k 5]
Index is JSON. Embeddings are optional: if the bge-m3 server is down, BM25 is used.
"""
import argparse, glob, json, math, os, re, sys, urllib.request

EMBED_URL = os.environ.get("L1_EMBED_URL", "http://127.0.0.1:8082/v1/embeddings")
DEFAULT_OUT = os.environ.get("L1_RAG_INDEX", "/tmp/nox_l1_rag_index.json")
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text):
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1]


def chunk_text(text, size=900):
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) > size:
            chunks.append(cur.strip())
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def embed(texts, url=EMBED_URL, timeout=5):
    """Return list of vectors or None if the server is unavailable."""
    try:
        body = json.dumps({"model": "bge-m3", "input": texts}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)["data"]
        return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]
    except Exception:
        return None


def build_index(root, use_embed=True):
    docs = []
    for path in sorted(glob.glob(os.path.join(root, "coordination", "*.md"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        rel = os.path.relpath(path, root)
        for i, c in enumerate(chunk_text(text)):
            docs.append({"src": rel, "n": i, "text": c, "tok": tokenize(c)})
    mode = "bm25"
    if use_embed and docs:
        vecs = []
        for i in range(0, len(docs), 16):
            v = embed([d["text"] for d in docs[i:i + 16]])
            if v is None:
                vecs = None
                break
            vecs.extend(v)
        if vecs:
            for d, v in zip(docs, vecs):
                d["vec"] = v
            mode = "bge-m3"
    return {"mode": mode, "docs": docs}


def bm25_scores(index, query, k1=1.5, b=0.75):
    docs = index["docs"]
    n = len(docs)
    if not n:
        return []
    avg = sum(len(d["tok"]) for d in docs) / n or 1
    df = {}
    for d in docs:
        for t in set(d["tok"]):
            df[t] = df.get(t, 0) + 1
    q = tokenize(query)
    out = []
    for d in docs:
        tf = {}
        for t in d["tok"]:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d["tok"]) / avg))
        out.append(s)
    return out


def cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def search(index, query, k=5, use_embed=True):
    scores = None
    if use_embed and index.get("mode") == "bge-m3":
        qv = embed([query])
        if qv:
            scores = [cosine(qv[0], d["vec"]) for d in index["docs"]]
    if scores is None:  # safe fallback
        scores = bm25_scores(index, query)
    ranked = sorted(zip(scores, index["docs"]), key=lambda x: -x[0])[:k]
    return [{"score": round(s, 4), "src": d["src"], "n": d["n"], "text": d["text"]}
            for s, d in ranked if s > 0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index")
    pi.add_argument("--root", default=os.getcwd())
    pi.add_argument("--out", default=DEFAULT_OUT)
    pi.add_argument("--no-embed", action="store_true")
    pq = sub.add_parser("query")
    pq.add_argument("text")
    pq.add_argument("--out", default=DEFAULT_OUT)
    pq.add_argument("-k", type=int, default=5)
    pq.add_argument("--no-embed", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "index":
        idx = build_index(a.root, not a.no_embed)
        tmp = a.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False)
        os.replace(tmp, a.out)
        print("indexed %d chunks, mode=%s -> %s" % (len(idx["docs"]), idx["mode"], a.out))
    else:
        with open(a.out, encoding="utf-8") as f:
            idx = json.load(f)
        for r in search(idx, a.text, a.k, not a.no_embed):
            print("%.3f [%s#%d] %s" % (r["score"], r["src"], r["n"], r["text"][:200].replace("\n", " ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
