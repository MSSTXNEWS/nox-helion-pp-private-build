export RUNNER_TRACKING_ID=""
echo "C300: tr_img5"
N=/workspace/nox; F=$N/imgsvc/image_service.py; PY=$N/venv/bin/python
OLD=71460; ps -p $OLD -o args= | grep -q image_service.py || { echo "pid изменился"; ps -eo pid,args | grep "[i]mage_service"; }
ENVV=$(tr '\0' '\n' < /proc/$OLD/environ | grep -E '^(CUDA_|LD_LIBRARY_PATH|PATH=|NOX_)' | sed 's/=.*//' | tr '\n' ' '); echo "env-ключи (только имена): $ENVV"
kill $OLD; for i in $(seq 15); do kill -0 $OLD 2>/dev/null || break; sleep 1; done
(set -a; eval "$(tr '\0' '\n' < /proc/$$/environ >/dev/null 2>&1; true)"; set +a; cd $N/imgsvc && setsid -f nohup $PY -I $F >> $N/imgsvc/image_service.out 2>&1 < /dev/null)
sleep 6; ps -eo pid,etimes,args | grep "[i]mage_service.py" | cut -c1-120; curl -s -m5 localhost:8500/health | head -c 200; echo
echo END
