echo "C300: srv_k53"
N=/workspace/nox; D=$N/ops/dpo
pkill -9 -f chain_full.sh; sleep 1
pkill -f "train_dpo.py"; sleep 8
pgrep -fa "train_dpo|chain_full" | head -3
cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo
for f in train_dpo.py chain2.sh; do curl -s -m 30 "$R/$f?cb=$cb" -o $D/$f; done; chmod +x $D/chain2.sh
grep -c "a.steps \* a.accum" $D/train_dpo.py; ls $N/STOP
rm -f $D/run.lock
nohup setsid $D/chain2.sh </dev/null >/dev/null 2>&1 &
sleep 3; pgrep -f chain2.sh | head -1
