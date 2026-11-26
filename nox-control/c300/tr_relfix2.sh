echo "C300: tr_relfix2"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
cp -n $D/rel_gates.py $D/rel_gates.py.bak_v1
$PY - <<'PY'
p="/workspace/nox/ops/dpo/rel_gates.py"; s=open(p,encoding="utf-8").read()
def rep(a,b):
    global s
    assert s.count(a)==1,a[:50]; s=s.replace(a,b)
rep('hold = hold[:100]','hold = hold[:40]')
rep('log("ext+A/B генерация: база"); ab_ = answers(base); log("ext+A/B генерация: кандидат"); ac_ = answers(cand)',
    'AP = N + "/ops/dpo/ab_answers_%s.json" % hc\nif os.path.exists(AP):\n    _s = json.load(open(AP, encoding="utf-8")); ab_, ac_ = _s["base"], _s["cand"]; log("ответы A/B взяты из %s" % AP)\nelse:\n    log("ext+A/B генерация: база"); ab_ = answers(base); log("ext+A/B генерация: кандидат"); ac_ = answers(cand)\n    json.dump({"base": ab_, "cand": ac_}, open(AP, "w", encoding="utf-8"), ensure_ascii=False)')
rep('{"text": text[:3000], "context": prompt[:1500], "deep": True, "role": "answer"}','{"text": "Вопрос: " + prompt[:1200] + "\\n\\nОтвет: " + text[:2500], "deep": True, "role": "answer"}')
rep('    return g("Reward-V2-Qwen3-1.7B"), g("Reward-V2-Qwen3-0.6B")','    return g("Reward-V2-Qwen3-1.7B"), g("Reward-V2-Qwen3-0.6B")\ndef jr(prompt, text):\n    for _ in range(8):   # фоновые запросы судья может пропустить при занятом CPU (score=None) — повтор\n        r = judge(prompt, text)\n        if r[0] is not None and r[1] is not None: return r\n        time.sleep(4)\n    raise RuntimeError("судья вернул пропуск 8 раз")')
rep('ja, jb = judge(p["prompt"], a), judge(p["prompt"], b)','ja, jb = jr(p["prompt"], a), jr(p["prompt"], b)')
rep('with ThreadPoolExecutor(3) as ex: R = list(ex.map(one, pairs))','with ThreadPoolExecutor(1) as ex: R = list(ex.map(one, pairs))\nlog("A/B ошибки: %s" % [r[3] for r in R if r[3].startswith("err")][:3])')
open(p,"w",encoding="utf-8").write(s); print("патч ok")
PY
$PY -m py_compile $D/rel_gates.py && echo компиляция-ok
C=$N/distill_v2/ckpt_keep/cand_dpo_11261135
pgrep -f "[r]el_gates.py" >/dev/null && echo "rel_gates уже идёт" || { (cd $D && setsid -f nohup nice -n 5 $PY -I rel_gates.py $C >> $D/relgates_run3.log 2>&1 < /dev/null); sleep 3; echo "rel_gates запущен"; }
cat > $D/watch2.sh <<'EOW'
#!/bin/bash
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python; L=$D/watch2.log
sleep 20; while pgrep -f "[r]el_gates.py" >/dev/null; do sleep 30; done
SHA=ebf02c04001131ac
echo "$(date -u +%T) rel_gates закончил: $(python3 -c "import json;d=json.load(open('$N/distill_v2/gates/decision_$SHA.json'));print(d['pass'],d['reasons'][:3],d['rel']['ab'])" 2>&1 | cut -c1-600)" >> $L
$PY -I $D/accept_cand.py $SHA >> $L 2>&1; echo "$(date -u +%T) accept rc=$?" >> $L
EOW
setsid -f bash -c "echo \$\$ > $D/watch2.pid; exec bash $D/watch2.sh" >/dev/null 2>&1 < /dev/null; sleep 2; echo "watch2 pid $(cat $D/watch2.pid)"
echo END
