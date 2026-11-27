echo "K1: l1_oa4"
echo "runner_uid=$(id -u)"; echo "oa_uid=$(stat -c %u /proc/$(supervisorctl pid nox_owner_active))"
tail -3 /workspace/nox/state/owner_active.log | cut -c1-120
