echo "C300: tr_chk2"
N=/workspace/nox; D=$N/ops/dpo
date -u; ps -eo pid,etimes,args | grep -E "rel_gates|build_dpo3|train_dpo" | grep -v grep | cut -c1-110
sed -n 108,118p $N/svc/pipeline/pipeline_svc.py | cut -c1-170
echo "-- build3"; tail -4 $D/build3.log | cut -c1-300
echo "-- relgates"; grep -a -E "^[0-9:]{8} " $D/relgates_run1.log | tail -6 | cut -c1-400
nvidia-smi --query-gpu=memory.used --format=csv,noheader; df -h /workspace | tail -1 | cut -c1-60
echo END
