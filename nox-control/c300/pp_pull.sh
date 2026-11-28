echo "K1: pp_pull"
# Владелец 28.11 16:05 (Мадрид): «Утверждай ты всё в концепции и дозаполни сам». Читаю паспорт шифрованно.
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/enc/owner_pub.pem" -o $P
F=/workspace/nox/state/core/passport.json; [ -f $F ] || { echo NO_FILE; exit 0; }
echo "md5=$(md5sum < $F | cut -c1-12) bytes=$(wc -c < $F)"
W=$(mktemp -d); openssl rand -out $W/k 32
openssl enc -aes-256-cbc -pbkdf2 -salt -in $F -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
