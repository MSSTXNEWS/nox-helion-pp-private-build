#!/bin/bash
N=/workspace/nox
echo "== binaries"; for b in supervisord supervisorctl s6-svscan pm2 node logrotate vector netdata redis-server rq huey_consumer promtail prometheus node_exporter lhci lighthouse promptfoo lm_eval litellm tmux cron crond runit; do p=$(command -v $b 2>/dev/null || ls $N/venv/bin/$b $N/venv_tools/bin/$b $N/agents/venv/bin/$b $N/tools/*/bin/$b 2>/dev/null | head -1); echo "$b: ${p:-нет}"; done
echo "== pip (venvs)"; for v in venv venv_tools agents/venv venv_living; do echo "[$v] $($N/$v/bin/pip list 2>/dev/null | grep -i -E '^(litellm|rq|huey|redis|supervisor|prometheus|trl|unsloth|axolotl|lm.eval|lm_eval|promptfoo|peft|psutil|apscheduler|celery|locust|opentelemetry)' | awk '{printf "%s=%s ",$1,$2}')"; done
echo "== stewards"; ls $N/stewards | head -40; wc -l $N/stewards/*.py 2>/dev/null | tail -1
echo "== .sh watchers"; ls $N/agent/*.sh $N/ops/*watch*.sh $N/ops/*guard*.sh 2>/dev/null | head -20
echo "== crontab"; crontab -l 2>/dev/null | grep -v '^#' | cut -c1-120 | head -15
echo "== supervisord confs"; ls /etc/supervisor/conf.d 2>/dev/null | head -20; find /etc /workspace/nox -maxdepth 3 -name "supervisord*.conf" 2>/dev/null | head -5
echo "== litellm"; ps -eo pid,etimes,args | grep -E "litellm|privacy_gw" | grep -v grep | cut -c1-170
sed -E 's/(api_key|key|token)[^\n]*/\1: ***/I' $N/router/config.yaml 2>/dev/null | head -40
echo "== flock/lock usage"; grep -rl "flock\|fcntl.lockf\|\.lock\b" $N/stewards $N/ops $N/agent --include=*.py --include=*.sh 2>/dev/null | grep -v bak | wc -l
echo "== biggest logs"; find $N -name "*.log" -size +50M -not -path "*/venv*" 2>/dev/null | xargs -r ls -laS 2>/dev/null | head -8 | awk '{print $5,$9}'
