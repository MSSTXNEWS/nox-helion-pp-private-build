echo "K1: iq10_rb"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
cp -a $F.bak_iq10 $F; echo "md5=$(md5sum <$F|cut -c1-8)"
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
echo END
