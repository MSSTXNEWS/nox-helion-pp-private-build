echo "K1: p5_fin"; export RUNNER_TRACKING_ID=""; N=/workspace/nox; A=$N/agent/autotrain; P=$N/state/p5; mkdir -p $P/slots
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/p5_bench.py -o /tmp/p5_bench.py
C=$A/donor_hybrid.cmd.p5_e1_ub2048; [ -s $C ] || { echo NOCMD; echo END; exit 0; }
if pgrep -f "train_dpo.py|distill_v2.py train" >/dev/null; then echo "train_active -> только запись p5_best, без рестарта"; cp $C $A/donor_hybrid.cmd.p5_best; echo END; exit 0; fi
curl -s -m20 -X POST "localhost:8104/slots/0?action=save" -H 'Content-Type: application/json' -d '{"filename":"front0.bin"}' -o /dev/null -w "slot_save=%{http_code}\n"
cp $C $A/donor_hybrid.cmd.p5_best
bash $N/ops/body_restart.sh --force --cmd $A/donor_hybrid.cmd.p5_best --reason "p5 final e1" 2>&1 | tail -1 | sed -E 's#/[^ ]*/#<d>/#g' | cut -c1-160
for i in $(seq 20); do curl -s -m2 localhost:8104/health | grep -q ok && break; sleep 2; done
curl -s -m30 -X POST "localhost:8104/slots/0?action=restore" -H 'Content-Type: application/json' -d '{"filename":"front0.bin"}' -o /dev/null -w "slot_restore=%{http_code}\n"
curl -s -X POST "localhost:8104/slots/0?action=save" -H 'Content-Type: application/json' -d '{"filename":"front0.bin"}' -o /dev/null -w "slot_save2=%{http_code}\n"
tr '\n' ' ' < $A/donor_hybrid.cmd.p5_best | sed -E 's#/[^ ]*/#<d>/#g'; echo
echo "health=$(curl -s -m3 localhost:8104/health)"; python3 /tmp/p5_bench.py fin quick 2>&1 | tail -1 | cut -c1-1500
echo END
