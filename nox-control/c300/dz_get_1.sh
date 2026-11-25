sleep 200
grep -v "^B64" /tmp/dz_qa_out.txt | cut -c1-1500 | sed 's/^/OUT: /' | tail -40
grep "^B64" /tmp/dz_qa_out.txt | cut -c1-120000
