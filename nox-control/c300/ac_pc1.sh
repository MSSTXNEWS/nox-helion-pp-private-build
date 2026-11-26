echo "C300: ac_pc1"
find /workspace/nox -maxdepth 3 -name "chat_core*" -not -path "*/node_modules/*" 2>/dev/null | head; 
grep -rlE "def (build|assemble|make)_?(prompt|messages)" /workspace/nox --include=*.py -s 2>/dev/null | grep -v "/venv\|backup\|\.bak" | head -10
curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;[print(s['id'],s['is_processing'],s.get('next_token',[{}])[0].get('n_decoded')) for s in json.load(sys.stdin)]"
ss -tnp 2>/dev/null | grep ":8104" | awk '{print $6}' | sort | uniq -c | head -5
