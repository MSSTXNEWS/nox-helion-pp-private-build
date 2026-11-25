echo "C300: d_s2"
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/d_svc_fix.sh -o /workspace/nox/svc/d_svc_fix.sh
nohup setsid bash /workspace/nox/svc/d_svc_fix.sh > /workspace/nox/svc/d_fix.out 2>&1 &
sleep 2; echo started
