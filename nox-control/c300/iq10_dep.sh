echo "K1: iq10_dep"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
curl -fsSL $R/logic20.json -o /tmp/l20.json; curl -fsSL $R/lg_test.py -o /tmp/lg.py
echo BEFORE; python3 /tmp/lg.py /tmp/l20.json | tee /tmp/lg_before | grep LOGIC
[ "$(md5sum < $F | cut -c1-32)" = 3a44dafc200f659b4e0fa14b3634d8bb ] || { echo "BASE_CHANGED abort"; echo END; exit 0; }
W=$(mktemp -d); curl -fsSL $R/enc_in/iq10.enc -o $W/e; curl -fsSL $R/enc_in/iq10.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; echo END; exit 0; }
[ "$(md5sum < $W/chat_core.py | cut -c1-32)" = d70de869b46a010b0f4ef5e2927b8b20 ] || { echo BAD_PAYLOAD; echo END; exit 0; }
python3 -m py_compile $W/chat_core.py || { echo COMPILE_FAIL; echo END; exit 0; }
cp -a $F $F.bak_iq10; cp $W/chat_core.py $F; rm -rf $W; echo applied
curl -sfL "$R/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 8; echo AFTER; python3 /tmp/lg.py /tmp/l20.json | tee /tmp/lg_after | grep LOGIC
b=$(grep -oE "LOGIC [0-9]+" /tmp/lg_before | cut -d' ' -f2); a=$(grep -oE "LOGIC [0-9]+" /tmp/lg_after | cut -d' ' -f2)
paste <(grep ^L /tmp/lg_before) <(grep ^L /tmp/lg_after) | awk '{print $1,$2,"->",$5}' | tr '\n' ' '; echo
if [ -z "$a" ] || [ "$a" -lt "$b" ]; then echo ROLLBACK; cp -a $F.bak_iq10 $F; pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1; fi
echo END
