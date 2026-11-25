sed -n 28,40p /workspace/nox/web/site/nox-chat-living.js | cut -c1-330 | sed 's/^/OUT: /'
grep -a "OUT:" /tmp/m_qa_out2.txt | grep -v " OK$" | cut -c1-260 | sed 's/^/OUT: Q430 /'
grep -a "OUT:" /tmp/m_qa_out.txt | grep -v " OK$" | cut -c1-260 | sed 's/^/OUT: Q390 /'
echo "OUT: ok430/768 $(grep -ac ' OK$' /tmp/m_qa_out2.txt) ok390 $(grep -ac ' OK$' /tmp/m_qa_out.txt)"
