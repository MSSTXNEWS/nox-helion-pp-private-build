echo "C300: v_diag_1"
A=/workspace/nox/advisors; ls -la $A 2>&1 | head; echo --- reg; cat $A/register.log 2>&1 | tail -30
echo --- health; curl -s -m5 127.0.0.1:8793/health; echo
pgrep -fa "advisors|gateway.py|register.py" | cut -c1-150 | head
echo --- SX; tail -c 900 /workspace/nox/svc/start_extra.sh
echo --- logs; tail -5 /workspace/nox/svc/logs/advisors.log 2>&1
ls -la /workspace/nox/state/secrets /workspace/nox/state/advisors* 2>&1 | head
grep advisors_gw /workspace/nox/web/pkg/server/svc_registry.json
