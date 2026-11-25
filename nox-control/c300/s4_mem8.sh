echo S4RUN:s4_mem8
timeout 60 find /workspace/nox /root/nox -name "events_bus.py" -o -name "recall_api.py" -o -name "s03_store.py" -o -name "memory_search.py" 2>/dev/null | grep -v "venv\|node_modules" | head -12
