#!/usr/bin/env bash
# Usage on the NOX server (as root):  curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/<SHA>/nox-control/cmd_agent/install.sh | bash -s <SHA> <ISSUE_NUMBER>
set -euo pipefail
SHA="$1"; ISSUE="$2"
mkdir -p /opt/nox-cmd /var/lib/nox /etc/nox
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$SHA/nox-control/cmd_agent/nox_cmd_agent.py" -o /opt/nox-cmd/agent.py
python3 -c "import cryptography" 2>/dev/null || pip install -q --break-system-packages cryptography || pip install -q cryptography
read -rsp "Paste GitHub fine-grained token (Issues: Read+Write, this repo only): " TOK < /dev/tty; echo
umask 077; printf 'NOX_GH_TOKEN=%s\nNOX_RESULT_ISSUE=%s\n' "$TOK" "$ISSUE" > /etc/nox/cmd_agent.env
cat > /opt/nox-cmd/run.sh <<'EOF'
#!/usr/bin/env bash
set -a; . /etc/nox/cmd_agent.env; set +a
exec python3 /opt/nox-cmd/agent.py
EOF
chmod 700 /opt/nox-cmd/run.sh
pkill -f /opt/nox-cmd/agent.py 2>/dev/null || true
if [ -d /etc/supervisor/conf.d ]; then
  printf '[program:nox-cmd-agent]\ncommand=/opt/nox-cmd/run.sh\nautostart=true\nautorestart=true\n' > /etc/supervisor/conf.d/nox-cmd-agent.conf
  supervisorctl reread >/dev/null 2>&1 && supervisorctl update >/dev/null 2>&1 || setsid nohup /opt/nox-cmd/run.sh >/var/log/nox-cmd.log 2>&1 &
else
  setsid nohup /opt/nox-cmd/run.sh >/var/log/nox-cmd.log 2>&1 &
fi
sleep 2; pgrep -fa /opt/nox-cmd/agent.py && echo "NOX cmd agent INSTALLED" || echo "NOT RUNNING - see /var/log/nox-cmd.log"
