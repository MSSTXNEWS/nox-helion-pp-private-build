echo "C300: u_rec3"
S=/workspace/nox/web/site; cd $S
echo "== 8080"; curl -s -m 8 -i localhost:8080/web/index.html | head -8 | cut -c1-160; cat /opt/supervisor-scripts/caddy.sh | head -20 | cut -c1-200; find / -maxdepth 3 -name "Caddyfile*" 2>/dev/null | head
echo "== qa_audit"; head -30 /workspace/nox/qa_audit.py | cut -c1-220; grep -n "argv\|argparse\|add_argument\|environ" /workspace/nox/qa_audit.py | head -12 | cut -c1-200
echo "== chat5"; wc -c nox-chat-5.js; head -c 1800 nox-chat-5.js; echo; grep -o "id=\"[a-zA-Z0-9_-]*\"" nox-chat-5.js | sort -u | head -30 | tr '\n' ' '
echo; echo "== nai-btn"; grep -ho "[^}]*\.nai-btn[^}]*}" *.css | head -4 | cut -c1-250
