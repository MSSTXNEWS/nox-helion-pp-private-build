#!/bin/bash
cat /etc/supervisor/conf.d/nox_sun_adapter.conf | sed -E 's/(KEY|TOKEN|SECRET)[A-Za-z_]*="[^"]*"/\1=***/g' | cut -c1-200
ls /etc/supervisor/; grep -n -E "^\[(unix_http|supervisorctl|include)" -A3 /etc/supervisor/supervisord.conf | head -14
(timeout 25 apt-get --version | head -1; timeout 20 apt-cache policy logrotate 2>&1 | head -3)
$HOME/../workspace/nox/venv/bin/pip download lm_eval --no-deps -d /tmp/x -q 2>&1 | tail -1
tail -4 /workspace/nox/agent/out/cascade_watchdog.log | cut -c1-100
cat /workspace/nox/state/p3/persona_gen3.json; echo; tail -c 300 /workspace/nox/state/p3/persona_gen3.out
