echo "K1: qa_stop1"
N=/workspace/nox
for f in $N/agent/out/u_audit3.sh $N/agent/out/u_audit4.sh $N/agent/out/u_audit5.sh $N/agent/out/u_audit6.sh $N/agent/out/ux_aud_p1.sh $N/agent/out/ux_aud_p2.sh $N/agent/out/ux_fast1.sh /tmp/ch_qa_run.sh; do [ -f "$f" ] && mv "$f" "$f.disabled" && echo "disabled $(basename $f)"; done
for p in u_audit ux_aud_p ux_fast1 ch_qa_run qa_audit.py chrome-headless-shell; do pkill -f "$p" 2>/dev/null; done
sleep 3
echo "left: audit=$(pgrep -fc 'u_audit|ux_aud|ux_fast1|ch_qa_run|qa_audit') chrome=$(pgrep -fc chrome-headless) load=$(cut -d' ' -f1 /proc/loadavg)"
