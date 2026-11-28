echo "K1: s6l_f1"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
P=$(mktemp); curl -fsSL $R/bundles/enc/s6_pub.pem -o $P; W=$(mktemp -d)
head -n 46 $N/state/s6/exam_base_snapshot.keep > $W/a.txt; ls -la $W/a.txt | awk '{print $5}'
openssl rand -out $W/k 32; openssl enc -aes-256-cbc -pbkdf2 -salt -in $W/a.txt -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"; echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"; rm -rf $W $P; echo END
