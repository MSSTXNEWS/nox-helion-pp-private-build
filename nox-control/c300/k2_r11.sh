echo "C300: k2_r11"
N=/workspace/nox
sed -n 140,265p $N/ops/draw/invoke_draw.py | cut -c1-260
echo "--- invokeai parent"; ps -o pid,ppid,args -p 3781299 | cut -c1-160; ps -o pid,args -p $(ps -o ppid= -p 3781299) | cut -c1-160
grep -rIl "invokeai-web\|invoke_root" /etc/supervisor/conf.d $N/ops/*.sh $N/svc/*.sh $N/agent/*.sh 2>/dev/null | head -5; crontab -l | grep -c invoke
ls -la $N/models/flux | cut -c1-150
