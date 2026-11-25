curl -s -o /dev/null -w "OUT: server %{http_code}\n" 127.0.0.1:8091/web/index.html; grep -c "ok\|OK" /tmp/m_qa_out4.txt 2>/dev/null
