cd /workspace/nox
grep -n "NICHE" qa_audit.py | head -5
sed -n '/^NICHE/,/^}/p' qa_audit.py | cut -c1-200 | head -60
cat qa_audit_loop.sh | head -20
