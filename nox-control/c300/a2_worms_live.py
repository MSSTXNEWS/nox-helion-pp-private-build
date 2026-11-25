#!/usr/bin/env python3
"""Живой цикл червей: кандидат -> карточка -> approve -> staging+SHA -> STOP на большом -> самоулучшение -> идеи. Лог в stdout."""
import json, time, os, sqlite3, urllib.request, urllib.parse, hashlib, shutil, subprocess
B = 'http://127.0.0.1:8810'; ST = '/workspace/nox/state'; DBW = '/workspace/nox/agents/worms.sqlite'
def api(m, p, body=None, t=60):
    rq = urllib.request.Request(B + p, method=m, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
    try: return json.loads(urllib.request.urlopen(rq, timeout=t).read())
    except Exception as e: return {'err': str(e)[:150]}
def hf(u): return json.loads(urllib.request.urlopen(urllib.request.Request('https://huggingface.co/api/' + u, headers={'User-Agent': 'nox-worm/1'}), timeout=30).read())
OK = {'apache-2.0', 'mit', 'bsd-3-clause', 'cc-by-4.0'}
def pick(lo, hi, skip=()):
    for m in hf('models?filter=safetensors&sort=downloads&limit=60&full=true&config=false'):
        sib = [s['rfilename'] for s in m.get('siblings', [])]; lic = next((t.split(':')[1] for t in m.get('tags', []) if t.startswith('license:')), '')
        if lic not in OK or m['id'] in skip or any(f.lower().endswith(('.bin', '.pt', '.pth', '.pkl', '.ckpt')) for f in sib): continue
        try: info = hf('models/' + m['id'] + '?blobs=true')
        except Exception: continue
        for s in info.get('siblings', []):
            if s['rfilename'].endswith(('.safetensors', '.gguf')) and lo <= (s.get('size') or 0) <= hi: return m['id'], lic, [x['rfilename'] for x in info['siblings'] if x['rfilename'].endswith(('.safetensors', '.gguf'))], s['rfilename'], s['size']
    return None
def addc(name, lic, files):
    c = sqlite3.connect(DBW); c.execute('INSERT OR REPLACE INTO finds(ts,src,name,url,license,size_gb,files,verdict,score,status,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)', (time.time(), 'hf', name, 'https://huggingface.co/' + name, 'лицензия ' + lic, 0, json.dumps(files[:6]), 'допущено', 9.0, 'candidate', 'тест цикла A2')); c.commit()
    return c.execute('SELECT id FROM finds WHERE name=?', (name,)).fetchone()[0]
def status(fid): return dict(zip(('status', 'sha', 'note'), sqlite3.connect(DBW).execute('SELECT status,sha,note FROM finds WHERE id=?', (fid,)).fetchone()))
st = os.statvfs('/workspace'); print('DISK free GB', round(st.f_bavail * st.f_frsize / 1e9, 1), flush=True)
tiny = pick(1 << 20, 80 << 20); print('TINY', tiny, flush=True)
big = pick(300 << 20, 1500 << 20, skip=(tiny[0] if tiny else '',)); print('BIG', big, flush=True)
if tiny:
    fid = addc(tiny[0], tiny[1], [tiny[3]]); cards = api('GET', '/worms/cards'); print('CARD', [c['text'] for c in cards.get('hunt', []) if c['id'] == fid], flush=True)
    t0 = time.time(); print('APPROVE', api('POST', '/worms/approve', {'id': fid, 'yes': True}), flush=True)
    for _ in range(60):
        s = status(fid)
        if s['status'] in ('absorbed', 'failed'): break
        time.sleep(2)
    print('STAGING', s['status'], round(time.time() - t0, 1), 's', 'sha', (s['sha'] or '')[:16], s['note'][-120:], flush=True)
    d = '/workspace/nox/worm_staging/' + tiny[0].replace('/', '__'); fl = os.listdir(d) if os.path.isdir(d) else []
    if fl and s['sha']: print('SHA check', hashlib.sha256(open(os.path.join(d, fl[0]), 'rb').read()).hexdigest() == s['sha'], fl, flush=True)
if big:
    bid = addc(big[0], big[1], [big[3]]); print('APPROVE big', api('POST', '/worms/approve', {'id': bid, 'yes': True}), 'size MB', big[4] >> 20, flush=True)
    time.sleep(5); t0 = time.time(); print('STOP', api('POST', '/worms/stop'), flush=True)
    for _ in range(100):
        s = status(bid)
        if s['status'] != 'downloading': break
        time.sleep(0.2)
    print('STOP latency', round(time.time() - t0, 2), 's ->', s['status'], s['note'][-60:], flush=True)
    api('POST', '/worms/start'); shutil.rmtree('/workspace/nox/worm_staging/' + big[0].replace('/', '__'), ignore_errors=True)
print('SCAN', api('POST', '/worms/scan', t=200), flush=True)
sc = api('GET', '/worms/cards'); print('SELF cards', sc.get('self'), flush=True)
if sc.get('self'):
    cid = sc['self'][0]['id']; print('SELF apply', api('POST', '/worms/self/approve', {'id': cid, 'yes': True}), flush=True)
    print('SELF rollback', api('POST', '/worms/self/rollback/%d' % cid), flush=True)
print('LEARNED', [x['text'][:90] for x in api('GET', '/worms/learned')][:5], flush=True)
print('AGENDA make', api('POST', '/worms/agenda/make', t=150), flush=True)
ag = api('GET', '/worms/agenda'); print('IDEAS', [(i['id'], i['title'][:50], i['status']) for i in ag.get('ideas', [])], flush=True)
if ag.get('ideas'): print('DEVELOP', api('POST', '/worms/develop', {'id': ag['ideas'][0]['id']}), flush=True)
print('WORMS_LIVE DONE', flush=True)
