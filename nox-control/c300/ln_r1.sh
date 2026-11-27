echo "K1: ln_r1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "== supervisor"; supervisorctl status 2>&1 | awk '{print $1,$2}' | head -80
echo "== ports"; ss -ltn | awk 'NR>1{print $4}' | sed 's/.*://' | sort -n | tr '\n' ' '
echo; echo "== disk"; df -BG --output=avail,pcent /workspace | tail -1
echo "== vram"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
echo "== N top"; ls $N | tr '\n' ' '
echo; echo "== web dir"; W=$(ls -d $N/web $N/site 2>/dev/null|head -1); echo $W; ls $W 2>/dev/null | grep -c html
echo "== find files"
find $N -maxdepth 4 \( -name 'passport.json' -o -name 'living_svc*' -o -name 'nox_inner_loop*' -o -name 'nox_mem*' -o -name 'selfheal*' -o -name 'disk_guard*' -o -name 'nox_canon*' -o -name 'owner_gate*' -o -name 'p3_axis_guard*' -o -name 'ext_eval*' -o -name 'char_cycle*' -o -name 'soul_backup*' -o -name 'relaunch.py' \) -not -path '*/node_modules/*' 2>/dev/null | head -40
echo "== crontab names"; crontab -l 2>/dev/null | grep -oE '[A-Za-z0-9_/.-]+\.(sh|py)' | sort -u | head -40
