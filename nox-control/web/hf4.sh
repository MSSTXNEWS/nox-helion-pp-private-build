#!/bin/bash
# stage4: чистка памяти от шаблона «Жду твой ввод…» (бэкап строк отдельно; в лог только счётчики) + проверка «привет» x3
TS=$(date +%Y%m%d%H%M%S)
python3 - <<P
import sqlite3, json, re, os
TS="$TS"
PAT=re.compile(r"Жду твой ввод|Пустота в очереди|Что хочешь\s*[:—-]?\s*→")
db='/root/nox/memory/s03.db'
c=sqlite3.connect(db, timeout=30); c.row_factory=sqlite3.Row
rows=[dict(r) for r in c.execute("select * from mem_episodes")]
hit=[r for r in rows if PAT.search(r.get('text') or '') or PAT.search(r.get('summary') or '')]
roles={}
for r in hit: roles[r['role']]=roles.get(r['role'],0)+1
print('episodes total',len(rows),'match',len(hit),'by role',roles)
dele=[r for r in hit if r['role']!='user']
print('to delete',len(dele),'kept (user-role)',len(hit)-len(dele))
bk='/root/nox/memory/hotfix_removed_episodes_%s.json'%TS
json.dump(dele,open(bk,'w',encoding='utf-8'),ensure_ascii=False); os.chmod(bk,0o600)
ids=[r['id'] for r in dele]
# fts: ссылки на эпизоды (ref) + страховка по тексту
fts=[tuple(x) for x in c.execute("select rowid,ref,body from mem_fts")]
fd=[x[0] for x in fts if PAT.search(x[2] or '') and not any(PAT.search(r['text'] or '') and r['role']=='user' and (r['text'] or '')[:60] in (x[2] or '') for r in hit if r['role']=='user')]
print('fts rows to delete',len(fd))
c.execute('begin immediate')
for i in ids: c.execute('delete from mem_episodes where id=?',(i,))
for rid in fd: c.execute('delete from mem_fts where rowid=?',(rid,))
c.commit()
left=sum(1 for r in c.execute("select text from mem_episodes") if PAT.search(r[0] or ''))
print('episodes left',c.execute('select count(*) from mem_episodes').fetchone()[0],'template left',left)
# chat_turns.jsonl
p='/root/nox/logs/chat_turns.jsonl'; L=open(p,encoding='utf-8').read().split('\n')
bad=[l for l in L if l and PAT.search(l)]; good=[l for l in L if not (l and PAT.search(l))]
import shutil; shutil.copy2(p,p+'.bak_hotfix_'+TS)
b2='/root/nox/logs/hotfix_removed_turns_%s.jsonl'%TS; open(b2,'w',encoding='utf-8').write('\n'.join(bad)+'\n'); os.chmod(b2,0o600)
open(p+'.tmp','w',encoding='utf-8').write('\n'.join(good)); os.replace(p+'.tmp',p)
print('turns removed',len(bad),'kept lines',len([l for l in good if l]))
P
ask(){ curl -sN -m90 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}],\"stream\":true,\"nox_mode\":\"fast\"}" | python3 -c "
import sys,json
t=''
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    t+=(o.get('message') or {}).get('content','')
    if o.get('error'): t+='[ERR '+str(o['error'])[:80]+']'
print(repr(t[:300]))"; }
for q in "привет" "привет" "привет" "как сервер?"; do echo "Q:$q -> $(ask "$q")"; done
