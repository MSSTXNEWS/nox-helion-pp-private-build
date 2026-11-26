echo "C300: k2_r7"
N=/workspace/nox; O=$N/agent/out
echo "--- selfheal procs"; ps -eo pid,ppid,etimes,args | grep -E "selfheal|svc_selfheal|canon_night" | grep -v grep | cut -c1-200
F=$N/canon_night/selfheal_supervisor.sh
sed -n 1,60p $F | cut -c1-230
echo ....; sed -n 90,135p $F | cut -c1-230
echo "--- who starts selfheal_supervisor"; grep -rIln "selfheal_supervisor" /etc/supervisor/conf.d $N/ops/*.sh $N/stewards/*.py $N/stewards/*.sh $N/agent/*.sh $N/canon_night/*.sh $N/agent/nox_ops/*.py $N/operators/*.sh 2>/dev/null | head
crontab -l | grep -n -E "selfheal|canon" | cut -c1-250
ls $N/state/locks 2>/dev/null; ls -la --time-style=full-iso $N/state/locks/core.lock 2>/dev/null
ls -la --time-style=full-iso $O/selfheal*.log $N/canon_night/*.log 2>/dev/null | cut -c30-200
tail -5 $O/selfheal_supervisor.log 2>/dev/null | cut -c1-200
