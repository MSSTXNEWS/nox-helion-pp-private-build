echo "K1: v1_02t"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
grep -n qa_audit $N/ops/p3_cpuset_guard.sh $N/stewards/chat_guard.py $N/svc/pipeline/acc1/run.sh | cut -c1-220
ls /tmp/ch_qa_run.sh; grep -c . /tmp/ch_qa_run.sh; grep -n -i "while\|loop\|sleep" /tmp/ch_qa_run.sh $N/agent/out/ux_fast1.sh $N/agent/out/u_audit6.sh | head -8 | cut -c1-160
ps -eo pid,etimes,args | grep -E "chat_guard|acc1" | grep -v grep | cut -c1-140
echo END
