echo "C300: srv_k149"
cd /workspace/nox/web/pkg/server
n=$(grep -n "def _p3_direct8104" chat_core.py | cut -d: -f1); sed -n "${n},$((n+28))p" chat_core.py | cut -c1-230
ss -ltn | grep -E ":8083 |:8793 " | awk '{print $4}'; curl -s -m4 http://127.0.0.1:8083/health | cut -c1-120; echo; curl -s -m4 http://127.0.0.1:8084/v1/rte/health | cut -c1-200
