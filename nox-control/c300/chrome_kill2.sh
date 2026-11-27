echo "K1: chrome_kill2"
for p in $(pgrep -f chrome-headless | head -3); do pp=$(ps -o ppid= -p $p | tr -d ' '); for i in 1 2 3 4 5; do n=$(ps -o comm= -p $pp 2>/dev/null); f=$(tr '\0' ' ' < /proc/$pp/cmdline 2>/dev/null | grep -oE '[A-Za-z0-9_./-]+\.(py|sh)' | head -1 | xargs -r basename); echo "chain $i $n $f"; pp=$(ps -o ppid= -p $pp 2>/dev/null | tr -d ' '); [ -z "$pp" ] || [ "$pp" = 1 ] && break; done; break; done
pkill -f chrome-headless; pkill -f qa_audit.py; sleep 2
echo "chrome_left=$(pgrep -fc chrome-headless) load=$(cut -d' ' -f1 /proc/loadavg)"
