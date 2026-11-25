echo "C300: d_s4"
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/d_svc_fix3.sh -o /workspace/nox/svc/d_svc_fix3.sh
nohup setsid bash /workspace/nox/svc/d_svc_fix3.sh > /workspace/nox/svc/d_fix3.out 2>&1 &
sleep 2; echo started
