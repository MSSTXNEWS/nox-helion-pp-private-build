echo "C300: srv_k9"
cd /workspace/nox/agents
cp nox_worms.py nox_worms.py.bak_k1_$(date +%s)
./venv/bin/pip install -q feedparser 2>&1 | tail -1
./venv/bin/python - <<'PY'
import re
p='nox_worms.py'; s=open(p,encoding='utf8').read()
def rep(a,b):
    global s
    assert s.count(a)==1,(s.count(a),a[:50]); s=s.replace(a,b)
rep("TOPICS = ['Qwen coder GGUF', 'UI generation Qwen', 'Russian LLM GGUF', 'tiny LLM router classifier', 'reranker GGUF']",
"TOPICS = ['Qwen coder GGUF', 'UI generation Qwen', 'Russian LLM GGUF', 'tiny LLM router classifier', 'reranker GGUF', 'MoE LoRA fine-tune', 'speculative decoding draft', 'text to image GGUF']")
rep("RSS = ['https://huggingface.co/blog/feed.xml']","RSS = ['https://huggingface.co/blog/feed.xml', 'https://hnrss.org/newest?q=LLM+OR+GGUF+OR+LoRA&points=40', 'http://export.arxiv.org/rss/cs.CL']")
rep("def hf_scan(llm):","""def _err(k, e):
    try: open(W + '/agents/worms.err', 'a').write(f'{k}: {e!r}'[:300] + '\\n')
    except Exception: pass
def _rot(): return int(time.time() // 1800)
def _hf_sort(): return ['trendingScore', 'createdAt', 'lastModified', 'likes', 'downloads'][_rot() % 5]
GHQ = ['llm agent', 'lora fine-tuning moe', 'gguf inference engine', 'russian llm', 'speculative decoding', 'diffusion cpp', 'rag reranker', 'kv cache quantization']
def hf_scan(llm):""")
rep("'sort': 'downloads', 'limit': 6, 'full': 'true'","'sort': _hf_sort(), 'limit': 12, 'full': 'true'")
i=s.index("def hf_scan"); j=s.index("except Exception: continue",i)
s=s[:j]+"except Exception as e: _err('hf', e); continue"+s[j+len("except Exception: continue"):]
rep("url = 'x'","url = 'x'") if False else None
rep("try: items = json.loads(http('https://api.github.com/search/repositories?q=llm+agent+license:apache-2.0+language:python&sort=stars&per_page=5'))['items']\n    except Exception: return 0",
"""try:
        _d = time.strftime('%Y-%m-%d', time.gmtime(time.time() - 14 * 86400))
        _qq = urllib.parse.quote(f'{GHQ[_rot() % len(GHQ)]} pushed:>{_d} stars:>30 license:apache-2.0') if False else urllib.parse.quote(f'{GHQ[_rot() % len(GHQ)]} pushed:>{_d} stars:>30')
        items = json.loads(http('https://api.github.com/search/repositories?q=' + _qq + '&sort=updated&per_page=10'))['items']
    except Exception as e: _err('github', e); return 0""")
rep("sc, jw = judge_text(llm, name, r.get('description') or '')","sc, jw = judge_text(llm, name, r.get('description') or '')\n        sc = sc if sc is None else float(sc or 0)")
i=s.index("def rss_scan"); j=s.index("def last_absorb")
s=s[:i]+'''def rss_scan(llm):
    if stopped() or not spend('rss_per_hour'): return 0
    n = 0
    for u in RSS:
        try:
            raw = http(u)
            try:
                import feedparser
                ents = [(e.get('title', ''), e.get('link', '')) for e in feedparser.parse(raw).entries[:6]]
            except ImportError:
                x = raw.decode('utf8', 'ignore'); ents = []
                for it in re.findall(r'<(?:item|entry)\\b.*?</(?:item|entry)>', x, re.S)[:6]:
                    t = re.search(r'<title[^>]*>(.*?)</title>', it, re.S); l = re.search(r'<link[^>]*?(?:href="([^"]+)"[^>]*|>\\s*([^<\\s]+)\\s*<)', it, re.S)
                    if t and l: ents.append((re.sub(r'<!\\[CDATA\\[|\\]\\]>', '', t.group(1)).strip(), l.group(1) or l.group(2)))
        except Exception as e: _err('rss', e); continue
        for t, l in ents:
            if not t or not l or q('SELECT 1 FROM finds WHERE src="rss" AND name=?', (t[:150],), one=True): continue
            q('INSERT OR IGNORE INTO finds(ts,src,name,url,verdict,score,status) VALUES(?,?,?,?,?,?,?)', (time.time(), 'rss', t[:150], l, 'новость', 5, 'info')); n += 1
    return n
'''+s[j:]
open(p,'w',encoding='utf8').write(s)
PY
./venv/bin/python -m py_compile nox_worms.py && echo COMPILED
./venv/bin/python - <<'PY'
import nox_worms as w
def llm(*a,**k): raise RuntimeError('stub')
print('TEST hf',w.hf_scan(llm),'gh',w.gh_scan(llm),'rss',w.rss_scan(llm))
PY
tail -3 worms.err
