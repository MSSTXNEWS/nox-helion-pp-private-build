echo "K1: tw1"
N=/workspace/nox; D=$N/ops/dpo; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; ts=$(date +%s)
W=$(mktemp -d); curl -fsSL $R/enc_in/tw1.enc -o $W/e; curl -fsSL $R/enc_in/tw1.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; exit 0; }
bash -n $W/char_cycle.sh || { echo SYNTAX_FAIL; exit 0; }
[ -f $N/agent/autotrain/donor_hybrid.cmd.gpu_ncmoe0 ] && [ -f $N/agent/autotrain/donor_hybrid.cmd.liska_ncmoe22 ] || { echo NO_CMDS; exit 0; }
cp -a $D/char_cycle.sh $D/char_cycle.sh.bak_tw1_$ts; cp $W/char_cycle.sh $D/char_cycle.sh; chmod +x $D/char_cycle.sh; echo "cycle_patched"
# новые пары just_model -> в обучающий набор (без дублей)
cp -a $D/dpo3_train.jsonl $D/dpo3_train.jsonl.bak_tw1_$ts
python3 - <<'PY'
import json
D="/workspace/nox/ops/dpo"; seen=set(); out=[]
for f in ("dpo3_train.jsonl","dpo4_jm.jsonl"):
    for l in open(D+"/"+f,encoding="utf-8"):
        l=l.strip()
        if not l: continue
        try: o=json.loads(l); k=json.dumps(o.get("prompt"),ensure_ascii=False)+json.dumps(o.get("chosen"),ensure_ascii=False)
        except Exception: continue
        if k in seen: continue
        seen.add(k); out.append(l)
open(D+"/dpo3_train.jsonl","w",encoding="utf-8").write("\n".join(out)+"\n"); print("dpo3_train_rows",len(out))
PY
touch $N/state/p3/dpo_pending; rm -rf $W
echo "owner_active_age_s=$(( $(date +%s) - $(stat -c %Y $N/state/orch/OWNER_ACTIVE 2>/dev/null || echo 0) ))"
echo END
