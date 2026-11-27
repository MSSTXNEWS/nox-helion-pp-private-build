echo "K1: l2_mem_dbg1"
N=/workspace/nox
curl -s -m 5 -XPOST 127.0.0.1:8082/embed -d '{"texts":["тест"]}' | head -c 120; echo
$N/venv_mem/bin/python - <<'PY'
import sys,traceback; sys.path.insert(0,"/workspace/nox/svc/mem")
try:
    import nox_mem as m; print(m.add_fact("Тестовый факт про кошку qa","qa-dbg"))
except Exception: traceback.print_exc()
PY
