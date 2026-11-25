pgrep -af dz_qa.py | head -3
grep -v "^B64" /tmp/dz_qa_out.txt | cut -c1-1200 | sed 's/^/OUT: /' | tail -40
grep "^B64" /tmp/dz_qa_out.txt | cut -c1-150000
