echo "C300: k2_r19"
N=/workspace/nox; A=$N/agent/autotrain
echo "phase: $(cat $N/state/gpu_phase)"; echo "mode: $(cat $A/mode)"; ls -la --time-style=full-iso $N/state/gpu_phase $A/mode | cut -c25-120
echo "--- donor_gpu.cmd"; tr '\n' ' ' < $A/donor_gpu.cmd | cut -c1-600; echo
echo "--- autotrain procs"; ps -eo pid,etimes,args | grep -E "autotrain|distill_v2" | grep -v grep | cut -c1-160
tail -12 $A/autotrain.log 2>/dev/null | cut -c1-200; ls $A | grep -E "\.log$|rounds" | head
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
