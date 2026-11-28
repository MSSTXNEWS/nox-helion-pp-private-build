echo "K1: s6l_d7"
N=/workspace/nox; D=$N/ops/dpo; P=$N/ops/persona; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
for f in persona_guard.py persona_exam.py; do curl -fsSL --retry 3 $RAW/s6l_files/$f -o $N/mods/$f && echo "ok $f $(md5sum < $N/mods/$f | cut -c1-8)"; done
W=$(mktemp -d); curl -fsSL $RAW/bundles/enc_in/pers2.enc -o $W/e; curl -fsSL $RAW/bundles/enc_in/pers2.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W && cp $W/persona_exam_set.json $P/persona_exam_set.json && chmod 600 $P/persona_exam_set.json && echo "exam_set updated $(stat -c %s $P/persona_exam_set.json)"; rm -rf $W
(cd $N/mods && python3 -I -m pytest -q tests/test_persona_guard.py 2>&1 | tail -1)
echo "open_proc=$(pgrep -f s6_open.py | wc -l)"; ls -la $D/pers1_open* 2>/dev/null | awk '{print $5,$9}'; tail -c 500 $D/s6_open.log
if [ "$(pgrep -f s6_open.py | wc -l)" = 0 ]; then python3 -I $D/s6_assemble.py 2>&1 | tail -4; fi
echo END
