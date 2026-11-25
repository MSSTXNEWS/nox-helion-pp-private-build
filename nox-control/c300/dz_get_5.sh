for i in $(seq 1 27); do grep -q "OUT_END\|Traceback" /tmp/dz_qa_out.txt 2>/dev/null && break; sleep 10; done
grep -v "^B64" /tmp/dz_qa_out.txt | cut -c1-1500 | sed 's/^/OUT: /' | tail -40
grep "^B64" /tmp/dz_qa_out.txt | cut -c1-150000
