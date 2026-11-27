export RUNNER_TRACKING_ID=""
echo "C300: tr_img4"
ps -o pid,ppid,etimes,args -p 71460 | cut -c1-160; PP=$(ps -o ppid= -p 71460 | tr -d ' '); ps -o pid,ppid,args -p $PP | cut -c1-160
supervisorctl status 2>&1 | awk '{print $1,$2}' | tr '\n' ';' | cut -c1-900; echo
grep -rl "image_service.py" /workspace/nox/ops/*.sh /workspace/nox/stewards/* /etc/supervisor/conf.d/* /workspace/nox/imgsvc/*.sh 2>/dev/null | head -5
echo END
