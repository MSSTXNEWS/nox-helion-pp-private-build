echo "C300: a2_diag2"
A=/workspace/nox/agents; pgrep -af 'nox_agents' | cut -c1-120; ls -la $A/nox_agents.py; grep -c "ALTER TABLE tasks ADD COLUMN prio" $A/nox_agents.py
tail -25 $A/service.log | cut -c1-220
