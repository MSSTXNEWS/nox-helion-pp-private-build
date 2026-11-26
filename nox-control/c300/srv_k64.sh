echo "C300: srv_k64"
cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo; D=/workspace/nox/ops/dpo
for f in ext_cases.py build_dpo2.py ext_eval.py chain4.sh; do curl -s -m 30 "$R/$f?cb=$cb" -o $D/$f; done; chmod +x $D/chain4.sh; wc -l $D/ext_cases.py $D/build_dpo2.py $D/ext_eval.py $D/chain4.sh | tail -5
cd $D; /workspace/nox/venv/bin/python -I -m py_compile ext_cases.py build_dpo2.py ext_eval.py && echo COMPILED
/workspace/nox/venv/bin/python -I -c "
import sys;sys.path[:0]=['/workspace/nox/brain/SLP','$D']
import fidelity_test as FT, ext_cases as E
c=E.ext_cases(); print(len(c)); print(FT.rule_check(c[0],'Я не уверен, честно: это открытый вопрос.'))"
ls /workspace/nox/ops/dpo/dpo_train.jsonl /workspace/nox/STOP 2>&1 | head -3
tail -n 2 /workspace/nox/agent/out/autotrain.log | cut -c1-120
