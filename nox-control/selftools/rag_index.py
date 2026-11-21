"""rag_index: stdlib BM25 over file chunks; optional bge-m3 rerank via :8082 embeddings."""
import json
import math
import os
import re
import registry as R

TOK = re.compile(r"\w+", re.U)
EXTS = (".md", ".py", ".txt", ".json", ".sh", ".js")


def tokens(s):
    return [t.lower() for t in TOK.findall(s)]


def chunks(path, size=800):
    text = open(path, encoding="utf-8", errors="replace").read()
    buf, start, ln = "", 1, 1
    for line in text.splitlines(True):
        if len(buf) + len(line) > size and buf:
            yield start, buf
            buf, start = "", ln
        buf += line
        ln += 1
    if buf.strip():
        yield start, buf


def build_index(root, exts=EXTS):
    docs = []
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in {".git", "__pycache__", "node_modules"}]
        for f in sorted(fs):
            if f.endswith(exts):
                fp = os.path.join(d, f)
                if os.path.getsize(fp) > 1 << 20:
                    continue
                for ln, txt in chunks(fp):
                    docs.append({"file": os.path.relpath(fp, root), "line": ln, "text": txt, "tf": _tf(txt)})
    df = {}
    for dd in docs:
        for t in dd["tf"]:
            df[t] = df.get(t, 0) + 1
    avg = sum(sum(d["tf"].values()) for d in docs) / max(1, len(docs))
    return {"n": len(docs), "avgdl": avg, "df": df, "docs": docs}


def _tf(txt):
    tf = {}
    for t in tokens(txt):
        tf[t] = tf.get(t, 0) + 1
    return tf


def bm25(index, query, k=5, k1=1.5, b=0.75):
    N, avg = index["n"], index["avgdl"] or 1
    q = set(tokens(query))
    sc = []
    for i, d in enumerate(index["docs"]):
        dl = sum(d["tf"].values())
        s = 0.0
        for t in q:
            f = d["tf"].get(t)
            if f:
                n = index["df"][t]
                s += math.log(1 + (N - n + 0.5) / (n + 0.5)) * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avg))
        if s > 0:
            sc.append((s, i))
    sc.sort(reverse=True)
    return sc[:k]


def embed(texts, url, timeout=20):
    st, d = R.http_json(url.rstrip("/") + "/v1/embeddings", {"input": texts, "model": "bge-m3"}, timeout=timeout)
    if st != 200:
        return None
    return [x["embedding"] for x in d["data"]]


def cos(a, b):
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


@R.register("rag_index", "write", {"properties": {
    "action": {"type": "string", "enum": ["build", "query"]}, "root": {"type": "string", "default": "."},
    "index": {"type": "string", "default": "/root/nox/state/rag/index.json"}, "query": {"type": "string"},
    "k": {"type": "integer", "default": 5}, "embed_url": {"type": "string", "default": "http://127.0.0.1:8082"},
    "use_embeddings": {"type": "boolean", "default": True}}, "required": ["action"]},
    "build: BM25 index of root (writes index file unless dry_run). query: BM25 top-k, reranked by bge-m3 on :8082 if up (else mode=bm25).",
    action_modes={"query": "read"})
def rag_index(a):
    ip = R.safe_path(a["index"])
    if a["action"] == "build":
        root = R.safe_path(a["root"], must_exist=True)
        idx = build_index(root)
        res = {"ok": True, "chunks": idx["n"], "terms": len(idx["df"]), "index": ip, "dry_run": a["dry_run"]}
        if not a["dry_run"]:
            R.backup_file(ip)
            os.makedirs(os.path.dirname(ip), exist_ok=True)
            tmp = ip + ".tmp"
            json.dump(idx, open(tmp, "w"))
            os.replace(tmp, ip)
        return res
    if not a.get("query"):
        return R.fail("query required")
    if not os.path.exists(ip):
        return R.fail("no index at %s; run build" % ip)
    idx = json.load(open(ip))
    k = a["k"]
    top = bm25(idx, a["query"], k=k * 4 if a["use_embeddings"] else k)
    mode = "bm25"
    if a["use_embeddings"] and top:
        vecs = embed([a["query"]] + [idx["docs"][i]["text"][:1500] for _, i in top], a["embed_url"])
        if vecs:
            mode = "bm25+bge-m3"
            top = sorted(((cos(vecs[0], vecs[j + 1]), top[j][1]) for j in range(len(top))), reverse=True)[:k]
    top = top[:k]
    return {"ok": True, "mode": mode, "results": [
        {"score": round(s, 4), "file": idx["docs"][i]["file"], "line": idx["docs"][i]["line"], "text": idx["docs"][i]["text"][:400]} for s, i in top]}
