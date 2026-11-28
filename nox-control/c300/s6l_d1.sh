echo "K1: s6l_d1"
# Личность: деплой persona_guard/exam (новые файлы, chat_core не трогаем), расшифровка данных, сборка DPO (синтетика), фон: открытые наборы
export RUNNER_TRACKING_ID=""
N=/workspace/nox; REFX=${REF:-main}; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$REFX/nox-control/c300; D=$N/ops/dpo; P=$N/ops/persona
echo "disk_avail=$(df -BG --output=avail $N | tail -1)"
mkdir -p $N/mods/tests $P
for f in persona_guard.py persona_exam.py; do curl -fsSL --retry 3 $RAW/s6l_files/$f -o $N/mods/$f && echo "ok $f $(md5sum < $N/mods/$f | cut -c1-8)"; done
curl -fsSL --retry 3 $RAW/s6l_files/test_persona_guard.py -o $N/mods/tests/test_persona_guard.py
curl -fsSL --retry 3 $RAW/s6l_files/s6_open.py -o $D/s6_open.py; curl -fsSL --retry 3 $RAW/s6l_files/s6_assemble.py -o $D/s6_assemble.py
W=$(mktemp -d); curl -fsSL $RAW/bundles/enc_in/pers1.enc -o $W/e; curl -fsSL $RAW/bundles/enc_in/pers1.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; echo END; exit 0; }
cp $W/pers1_synth.jsonl $D/pers1_synth.jsonl; cp $W/persona_exam_set.json $P/persona_exam_set.json; chmod 600 $P/persona_exam_set.json; rm -rf $W
echo "synth_lines=$(wc -l < $D/pers1_synth.jsonl) exam_set_bytes=$(stat -c %s $P/persona_exam_set.json)"
cd $N/mods && python3 -I -m pytest -q tests/test_persona_guard.py 2>&1 | tail -2
python3 -I $N/mods/persona_exam.py --selftest
python3 -I $D/s6_assemble.py 2>&1 | tail -8
setsid nohup python3 -I $D/s6_open.py 140 > $D/s6_open.log 2>&1 < /dev/null &
sleep 20; tail -c 600 $D/s6_open.log
echo END
