echo "K1: p5_recon2"; N=/workspace/nox; A=$N/agent/autotrain
echo mode=$(cat $A/mode); ls -la --time-style=+%m%d-%H%M $A | grep -E "cmd|mode" | awk '{print $5,$6,$7}'
for f in donor_gpu.cmd donor_gpu.cmd.known_good donor_hybrid.cmd.gpu_ncmoe0; do echo "$f md5=$(md5sum < $A/$f | cut -c1-8) lines=$(wc -l < $A/$f)"; done
echo "--diff gpu.cmd vs ncmoe0:"; diff $A/donor_gpu.cmd $A/donor_hybrid.cmd.gpu_ncmoe0 | sed -E 's#/[^ ]*/#<d>/#g'
echo "--diff known_good vs gpu.cmd:"; diff $A/donor_gpu.cmd.known_good $A/donor_gpu.cmd | sed -E 's#/[^ ]*/#<d>/#g'
echo "--autotrain refs:"; grep -n -E "donor_.*cmd|body_restart|8104" $A/autotrain.sh | cut -c1-220 | head -20
echo "--gpu_phase.sh:"; cat $A/gpu_phase.sh | head -30 | cut -c1-200
echo "--env:"; cat $A/donor.env 2>/dev/null | sed -E 's/=.*/=<set>/'
echo "--lastlog:"; tail -3 $N/state/body_restart.log | cut -c1-250
echo "--loadtime:"; grep -E "load_tensors|model loaded|main: server is listening|n_ubatch|n_batch|CUDA0 compute buffer|KV buffer" $N/agent/out/donor_donor_gpu.log | head -12 | cut -c1-200
echo END
