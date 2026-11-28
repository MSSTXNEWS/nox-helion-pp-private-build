echo "K1: vo1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
W=$(mktemp -d); curl -fsSL $R/enc_in/vo1.enc -o $W/e; curl -fsSL $R/enc_in/vo1.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; exit 0; }
mkdir -p $N/mods; cp $W/mods/* $N/mods/; rm -rf $W; echo "mods=$(ls $N/mods | wc -l)"
cd $N/mods && timeout 1500 bash install_voice.sh dmitri --with-engine 2>&1 | grep -iE "rtf|sha256|ok|fail|error|wav|license" | sed -E 's/[0-9a-f]{64}/<sha:&>/' | cut -c1-200 | tail -15
echo "stt $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8093/health)"
echo END
