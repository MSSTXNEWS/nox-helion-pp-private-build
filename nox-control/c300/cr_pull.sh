echo "K1: cr_pull"
# Создатель 28.11 ~21:40 МСК: «Да, читай шифрованно» — код рисования/редактора/сайдкара, только шифрованно.
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/enc/owner_pub.pem" -o $P
cd /workspace/nox || exit 0
W=$(mktemp -d); F=$(ls -d imgsvc/*.py ops/draw/*.py mods/nox_sidecar*.py web/pkg/server/sidecar*.py 2>/dev/null; find web/site -maxdepth 1 -name 'editor*.html' -o -maxdepth 1 -name 'nox-editor*.js' -o -maxdepth 1 -name 'nox-dz-creative.js' 2>/dev/null)
tar czf $W/a.tgz $F 2>/dev/null; echo "files=$(tar tzf $W/a.tgz | wc -l) bytes=$(wc -c < $W/a.tgz)"
openssl rand -out $W/k 32; openssl enc -aes-256-cbc -pbkdf2 -salt -in $W/a.tgz -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
