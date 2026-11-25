echo "C300: d_s3"
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/d_svc_fix2.sh -o /workspace/nox/svc/d_svc_fix2.sh
nohup setsid bash /workspace/nox/svc/d_svc_fix2.sh > /workspace/nox/svc/d_fix2.out 2>&1 &
sleep 2; echo started
