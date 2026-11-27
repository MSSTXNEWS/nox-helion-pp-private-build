echo "K1: cx_pin5"
A=/workspace/nox/agent/autotrain; ts=$(date +%s)
for f in donor_hybrid.cmd donor_hybrid.cmd.known_good; do cp -a $A/$f $A/$f.bak_cxpin_$ts; cp $A/donor_hybrid.cmd.liska_ncmoe22 $A/$f; done
grep -c -- "--n-cpu-moe 22" $A/donor_hybrid.cmd $A/donor_hybrid.cmd.known_good
