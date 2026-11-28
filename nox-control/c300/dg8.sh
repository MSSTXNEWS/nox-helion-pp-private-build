echo "K1: dg8"; A=/workspace/nox/agent/autotrain; N=/workspace/nox
for f in liska_ncmoe22 gpu_ncmoe0; do echo "== $f lines=$(wc -l < $A/donor_hybrid.cmd.$f) bytes=$(wc -c < $A/donor_hybrid.cmd.$f)"; grep -o -- '-\{1,2\}\(n-cpu-moe\|ngl\|ncmoe\|override-tensor\|ot\|cpu-moe\)[ =][^ ]*' $A/donor_hybrid.cmd.$f | head -5; done
echo "dpo36 exists: $(ls $A/donor_hybrid.cmd.dpo_ncmoe36 2>&1 | wc -l) same_as_22=$(cmp -s $A/donor_hybrid.cmd.dpo_ncmoe36 $A/donor_hybrid.cmd.liska_ncmoe22 && echo 1 || echo 0)"
echo "procs: $(ps -eo pid,stat,etimes,args | grep -E 'char_cycle|train_dpo|autotrain' | grep -v grep | awk '{print $1,$2,$3,$4,$5}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
ls -l --time-style=+%H:%M:%S $A/char_cycle.log | awk '{print $6}'; date +%H:%M:%S
echo END
