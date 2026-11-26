pgrep -af "python -m cascade|cascade_watchdog" | cut -c1-100; ss -tlnp | grep ':8400 ' | cut -c1-110
supervisorctl status nox_cascade
