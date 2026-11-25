echo "C300: d_s1"
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/d_svc_install.sh -o /workspace/nox/svc/d_svc_install.sh
nohup setsid bash /workspace/nox/svc/d_svc_install.sh > /workspace/nox/svc/d_install.out 2>&1 &
sleep 2; echo started
