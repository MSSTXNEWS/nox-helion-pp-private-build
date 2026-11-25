echo S4RUN:s4_mem6
timeout 40 find /workspace/nox /root -maxdepth 5 \( -iname "s03*" -o -iname "*recall*" \) -not -path "*/venv/*" -not -path "*/node_modules/*" -not -path "*/vendor/*" 2>/dev/null | head -20
grep -rn "NOX_MEMORY_DB" /workspace/nox/integration /workspace/nox/state/web 2>/dev/null | head -3 | cut -c1-200
ls -la /workspace/nox/state/memory | head
