echo "K1: pp_push"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
F=$N/state/core/passport.json; echo "md5_before=$(md5sum < $F | cut -c1-12)"
[ "$(md5sum < $F | cut -c1-12)" = "d4c5c9ccfefb" ] || { echo BASE_CHANGED; echo END; exit 0; }
W=$(mktemp -d); curl -fsSL $R/enc_in/pp1.enc -o $W/e; curl -fsSL $R/enc_in/pp1.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; rm -rf $W; echo END; exit 0; }
python3 -c "import json;json.load(open('$W/passport.json'))" || { echo BADJSON; rm -rf $W; exit 0; }
B=$F.bak_$(date +%Y%m%d%H%M); cp -a $F $B; echo "backup_sha=$(sha256sum < $B | cut -c1-12)"
cp $W/passport.json $F; rm -rf $W
echo "md5_after=$(md5sum < $F | cut -c1-12) filled=$(python3 -c "
import json
d=json.load(open('$F'));n=[0,0]
def w(x):
  if isinstance(x,dict):
    [w(v) for v in x.values()]
  else:
    n[0]+=1; n[1]+= x not in (None,'',[]) and not (isinstance(x,str) and x.startswith('HOLD'))
w(d);print(f'{n[1]}/{n[0]}')")"
echo END
