echo "C300: d_tex1"
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/d_tex1_job.sh -o /workspace/nox/web/build_d_tex1_job.sh
nohup setsid bash /workspace/nox/web/build_d_tex1_job.sh > /workspace/nox/web/d_tex1.log 2>&1 &
sleep 3; echo started
