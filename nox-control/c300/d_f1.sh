echo "C300: d_f1"
B=/workspace/nox/web/build; mkdir -p $B
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/fetch_frontend_donors.sh -o $B/fetch_frontend_donors.sh
cd $B; nohup setsid bash fetch_frontend_donors.sh > fetch.log 2>&1 &
sleep 5; echo started
