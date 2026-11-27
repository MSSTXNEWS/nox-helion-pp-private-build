echo "K1: l2_mem_mig1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
sqlite3 $N/state/living/mem.db ".schema" 2>/dev/null | cut -c1-200 | head -12 || python3 -c "import sqlite3;print([r[0] for r in sqlite3.connect('$N/state/living/mem.db').execute('select sql from sqlite_master')])" | cut -c1-600
which supervisorctl; ls /etc/supervisor/conf.d 2>/dev/null | head; grep -l "svc/living\|living_svc" /etc/supervisor/conf.d/* $N/svc/start*.sh 2>/dev/null | head
tail -n 6 $N/svc/start_extra.sh | cut -c1-220
