echo "C300: ac_mb9"
F=/workspace/nox/distill_v2/code/distill_v2.py; V=/workspace/nox/venv/bin/python
cp -n $F $F.bak_accel_tokb_20261126
grep -q ACCEL_TOKB $F && { echo already; exit; }
$V -I - <<'PY'
F='/workspace/nox/distill_v2/code/distill_v2.py'
s=open(F,encoding='utf-8').read()
wrap='''# ACCEL_TOKB 26.11 (ускоритель): state/accel_tok_budget (число) поднимает --tok-budget, если он по умолчанию (4096). Авто-откат:
# маркер .trying остаётся после падения/убийства -> следующий запуск игнорирует настройку и пишет .failed. Ручной откат: rm state/accel_tok_budget
def cmd_train(a):
    _p = os.path.join(NOXD, "state", "accel_tok_budget")
    _on = False
    try:
        if os.path.exists(_p) and not os.path.exists(_p + ".failed") and a.tok_budget == 4096:
            if os.path.exists(_p + ".trying"):
                os.rename(_p + ".trying", _p + ".failed"); log("ACCEL_TOKB: прошлый запуск не завершился -> настройка отключена")
            else:
                a.tok_budget = int(open(_p).read().strip()); open(_p + ".trying", "w").write(str(a.tok_budget)); _on = True
                log("ACCEL_TOKB: tok_budget %d" % a.tok_budget)
    except Exception as e:
        log("ACCEL_TOKB: пропуск (%r)" % (e,))
    try:
        r = _cmd_train_orig(a)
    except BaseException:
        raise
    if _on:
        try: os.remove(_p + ".trying")
        except OSError: pass
    return r


'''
assert 'def cmd_train(a):' in s
s=s.replace('def cmd_train(a):',wrap+'def _cmd_train_orig(a):',1)
open(F,'w',encoding='utf-8').write(s)
PY
$V -I -m py_compile $F && echo compiled
grep -n "ACCEL_TOKB" $F | head -3
mkdir -p /workspace/nox/state; echo 8192 > /workspace/nox/state/accel_tok_budget
echo "was: $(grep -aE 'скорость' /workspace/nox/agent/autotrain/rounds/r038/train.log | tail -3 | cut -c1-110)"
