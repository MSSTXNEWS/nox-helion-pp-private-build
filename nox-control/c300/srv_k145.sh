echo "C300: srv_k145"
cd /workspace/nox/web/pkg/server
sed -n 455,500p chat_core.py | cut -c1-210
echo ====; sed -n 545,575p chat_core.py | cut -c1-210
grep -n "^RTE\|^CORE\|RTE =" chat_core.py | head -3
