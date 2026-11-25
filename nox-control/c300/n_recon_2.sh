echo "C300: n_recon_2"
cd /workspace/nox
df -BG /workspace | tail -1
for v in venv voice2_venv; do echo "== $v"; ./$v/bin/python -c "
import importlib
for m in ['torch','transformers','onnxruntime','apscheduler','sqlite3','fastapi','flask','aiohttp','sentence_transformers']:
    try:
        x=importlib.import_module(m); print(m, getattr(x,'__version__','ok'))
    except Exception as e: print(m,'NO')
import sqlite3; c=sqlite3.connect(':memory:'); c.execute('create virtual table t using fts5(a)'); print('fts5 ok')
" 2>&1 | tr '\n' ';'; echo; done
python3 -c "import sqlite3;c=sqlite3.connect(':memory:');c.execute('create virtual table t using fts5(a)');print('sys fts5 ok')"
ls memory | head; ls state | head -40; ls hf_home | head
echo "== rules"; head -c 2500 state/living/rules.md
echo "== run_turn"; sed -n 298,406p web/pkg/server/chat_core.py | cut -c1-220
echo "== endpoints"; grep -rn "nox/morning\|/outbox\|api/chat/send\|/api/chat/" web/pkg/server/*.py | head -15 | cut -c1-200
ls web/pkg/server | head -40
echo "== reg tail"; python3 -c "
import json;r=json.load(open('web/pkg/server/svc_registry.json'));k=list(r)[-1];print(k,r[k])"
