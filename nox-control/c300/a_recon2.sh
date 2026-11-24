S=/workspace/nox/web/site
cp -n /workspace/nox/qa_audit.py /workspace/nox/qa_audit.py.bak_a_1
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/qa_audit.py?a1" -o /tmp/qa_new.py && python3 -m py_compile /tmp/qa_new.py && cp /tmp/qa_new.py /workspace/nox/qa_audit.py && echo audit deployed
echo "=== chat.html"; cat $S/chat.html
echo "=== chat-x.js"; cat $S/nox-chat-x.js
