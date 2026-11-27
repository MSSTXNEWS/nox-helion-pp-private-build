echo "K1: qa_stop2"
N=/workspace/nox
for f in $(pgrep -af "qa_loop.sh|qa_ctl.py" | grep -oE '/[A-Za-z0-9_./-]+(qa_loop\.sh|qa_ctl\.py)' | sort -u); do [ -f "$f" ] && mv "$f" "$f.disabled" && echo "disabled $(basename $f)"; done
pkill -f qa_loop.sh; pkill -f qa_ctl.py; pkill -f chrome-headless
touch $N/state/deep_adv.off && echo "deep_adv=off"
sleep 3; echo "qa_left=$(pgrep -fc 'qa_loop|qa_ctl|chrome-headless') load=$(cut -d' ' -f1 /proc/loadavg)"
