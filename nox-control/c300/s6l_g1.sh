echo "K1: s6l_g1"
N=/workspace/nox; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
for f in persona_guard.py persona_roles.py interlocutor_model.py; do curl -fsSL --retry 3 $RAW/s6l_files/$f -o $N/mods/$f && echo "ok $f $(md5sum < $N/mods/$f | cut -c1-8)"; done
for f in test_persona_guard.py test_persona_roles.py test_interlocutor_model.py; do curl -fsSL --retry 3 $RAW/s6l_files/$f -o $N/mods/tests/$f; done
curl -fsSL --retry 3 $RAW/s6l_files/tpj_backtest.py -o $N/ops/dpo/tpj_backtest.py
mkdir -p $N/state/cvectors; for f in cv_human.txt cv_ai.txt cv_eval.jsonl run_cvgen.sh build_cv_pairs.py; do curl -fsSL --retry 3 $RAW/s6l_files/cv/$f -o $N/state/cvectors/$f; done; chmod +x $N/state/cvectors/run_cvgen.sh
echo "cv pairs $(wc -l < $N/state/cvectors/cv_human.txt) $(wc -l < $N/state/cvectors/cv_ai.txt)"
(cd $N/mods && python3 -I -m pytest -q tests/test_persona_guard.py tests/test_persona_roles.py tests/test_interlocutor_model.py 2>&1 | tail -2)
(cd $N/mods && python3 -I persona_roles.py)
python3 -I $N/ops/dpo/tpj_backtest.py
echo "persona.on exists: $([ -e $N/state/persona.on ] && echo yes || echo no)"
echo END
