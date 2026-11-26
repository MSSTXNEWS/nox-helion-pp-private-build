echo "C300: srv_k150"
cd /workspace/nox/web/pkg/server
sed -n 408,456p chat_core.py | cut -c1-260
