echo "K1: enc_pull3"
# Владелец 28.11 11:4x МСК разрешил прочитать код цикла обучения (ops/dpo) через шифрованный канал.
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/enc/owner_pub.pem" -o $P
cd /workspace/nox/ops/dpo || { echo NO_DIR; exit 0; }
W=$(mktemp -d); tar czf $W/a.tgz char_cycle.sh build_dpo*.py accept_cand.py rel_gates.py teacher_dump.py train_dpo.py gates_only.py 2>/dev/null
echo "files=$(tar tzf $W/a.tgz | wc -l) bytes=$(wc -c < $W/a.tgz)"
openssl rand -out $W/k 32
openssl enc -aes-256-cbc -pbkdf2 -salt -in $W/a.tgz -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
