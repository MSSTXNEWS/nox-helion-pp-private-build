echo "C300: w_b7"
ps -eo pid,ppid,lstart,cmd | grep '[c]addy run' | cut -c1-200
supervisorctl status nox_web_chat_auth nox_api_bridge
ss -ltnp | grep 18091 | cut -c1-200
for i in 1 2 3 4 5 6; do curl -s -m5 -o /dev/null -w '%{http_code} ' http://127.0.0.1:18091/api/training/status; done; echo
