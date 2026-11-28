echo "K1: s6l_d10"
N=/workspace/nox; D=$N/ops/dpo; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
W=$(mktemp -d); curl -fsSL $RAW/bundles/enc_in/pers3.enc -o $W/e; curl -fsSL $RAW/bundles/enc_in/pers3.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W && cp $D/pers1_synth.jsonl $D/pers1_synth.jsonl.v1 && cp $W/pers1_synth.jsonl $D/pers1_synth.jsonl && echo "synth replaced lines=$(wc -l < $D/pers1_synth.jsonl)"; rm -rf $W
echo "open_proc=$(pgrep -f s6_open.py | wc -l) watcher=$(pgrep -f s6_after_open | wc -l)"
[ "$(pgrep -f s6_open.py | wc -l)" = 0 ] && python3 -I $D/s6_assemble.py 2>&1 | tail -3
echo END
