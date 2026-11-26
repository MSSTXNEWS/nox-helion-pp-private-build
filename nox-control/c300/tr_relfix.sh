echo "C300: tr_relfix"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
$PY - <<'PY'
p="/workspace/nox/ops/dpo/rel_gates.py"; s=open(p,encoding="utf-8").read()
old='    def run(chat): return {c["id"]: chat(sysm + [{"role": "user", "content": c["prompt"]}]) for c in allp}\n'
new='    def run(chat):\n        o = {}\n        for c in allp:\n            try: o[c["id"]] = chat(sysm + [{"role": "user", "content": c["prompt"]}])\n            except G.Pending: pass\n        return o\n'
assert s.count(old)==1; s=s.replace(old,new)
s=s.replace("return G.drive(run, gen, time.time() + 5400)","return G.drive(run, gen, time.time() + 5400, max_iter=6)")
open(p,"w",encoding="utf-8").write(s); print("исправлено")
PY
$PY -m py_compile $D/rel_gates.py && echo ok
C=$N/distill_v2/ckpt_keep/cand_dpo_11261135
pgrep -f "[r]el_gates.py" >/dev/null && echo "rel_gates уже идёт" || { (cd $D && setsid -f nohup nice -n 5 $PY -I rel_gates.py $C >> $D/relgates_run2.log 2>&1 < /dev/null); sleep 3; echo "rel_gates запущен"; }
[ -f $D/watch1.pid ] && kill -0 $(cat $D/watch1.pid) 2>/dev/null && echo "watch1 идёт" || { setsid -f bash -c "echo \$\$ > $D/watch1.pid; exec bash $D/watch1.sh" >/dev/null 2>&1 < /dev/null; sleep 2; echo "watch1 pid $(cat $D/watch1.pid)"; }
echo END
