cd /workspace/nox/web/site; grep -n "nxmPill" nox-*.js nox-*.css | cut -c1-700; sed -n '15,35p;56,76p' /workspace/nox/qa_audit.py | cut -c1-260
