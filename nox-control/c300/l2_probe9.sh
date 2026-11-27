echo "K1: l2_probe9"
ps -eo pid,etimes,stat,args | grep -E "unify1|patch_living|living_svc|nox_mem|python3 -" | grep -v grep | cut -c1-200
curl -s -m 3 127.0.0.1:18220/health; echo
(echo > /dev/tcp/127.0.0.1/18215) 2>&1 && echo living_port_up
tail -n 5 /workspace/nox/svc/living/logs/living.log | cut -c1-200
ls -la /workspace/nox/state/living/*.bak_l2* /workspace/nox/svc/living/*.bak_l2* 2>&1 | cut -c1-150
