echo "K1: l2_recon1"
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
df -h /workspace | tail -1; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
wc -l $F; ls -la $N/web/state/chat_fast.off 2>&1 | head -1; ls $N/web/state | head -30
echo "--- defs"; grep -n -E "^def |^class |^async def |RECALL|recall|s03|MARK" $F | head -80
echo "--- s03"; find $N -name "s03*" -not -path "*/node_modules/*" 2>/dev/null | head; 
for d in $(find $N -name "s03*.db" 2>/dev/null | head -2); do ls -la $d; python3 - "$d" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]); 
for r in c.execute("select name,sql from sqlite_master where type in('table','view')"): print(r[0], (r[1] or '')[:300].replace('\n',' '))
for (t,) in c.execute("select name from sqlite_master where type='table' and name not like '%\\_%' escape '\\'"):
    try: print(t, c.execute(f"select count(*) from {t}").fetchone())
    except Exception as e: print(t,e)
PY
done
echo "--- models"; find $N/models /workspace -maxdepth 4 \( -iname "*bge*" -o -iname "*reranker*" -o -iname "*t-one*" -o -iname "*silero*" -o -iname "*whisper*" \) 2>/dev/null | head -20
echo "--- py"; for p in python3 $N/venv/bin/python; do echo $p; $p -c "import sys;print(sys.version)"; $p -m pip list 2>/dev/null | grep -i -E "mem0|graphiti|letta|sqlite|sentence|FlagEmb|torch|pipecat|faster|onnx|llama|transformers|numpy|fastapi|qdrant|chroma" ; done
echo "--- ports"; ss -ltn | awk '{print $4}' | grep -E ":(8[0-9]{3}|9[0-9]{3}|18[0-9]{3}|7[0-9]{3})$" | tr '\n' ' '
echo; ps aux | grep -i -E "bge|embed|rerank" | grep -v grep | cut -c1-200 | head
