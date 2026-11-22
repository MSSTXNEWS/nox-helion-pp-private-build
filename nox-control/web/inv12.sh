#!/bin/bash
# только код и счётчики; содержимое чатов в лог не выводим (репозиторий публичный)
cd /root/nox
sed -n 240,285p web_server.py | cut -c1-330
echo "== front"; ls web | head -40; grep -ln "message.content\|\.message\b" web/*.js | head; grep -n "message" web/nox-newchat.js 2>/dev/null | cut -c1-240 | head -12
echo "== memory counts"; echo "turns-log: $(grep -c 'Жду твой ввод' logs/chat_turns.jsonl)"; python3 - <<'P'
import sqlite3
try:
    c=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True)
    for (t,) in c.execute("select name from sqlite_master where type='table'"):
        try:
            for col in [r[1] for r in c.execute('pragma table_info(%s)'%t)]:
                n=c.execute("select count(*) from %s where cast(%s as text) like '%%Жду твой ввод%%' or cast(%s as text) like '%%Пустота в очереди%%'"%(t,col,col)).fetchone()[0]
                if n: print('db',t,col,n)
        except Exception: pass
    print('tables checked')
except Exception as e: print('db err',e)
P
