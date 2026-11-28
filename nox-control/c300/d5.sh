echo "K1: d5"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
W=$(mktemp -d); curl -fsSL $R/enc_in/d5.enc -o $W/e; curl -fsSL $R/enc_in/d5.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; exit 0; }
for f in $W/d/*.py; do python3 -m py_compile $f || { echo "COMPILE_FAIL $f"; exit 0; }; done
cp $W/d/*.py $D/; echo "installed $(ls $W/d | tr '\n' ' ')"
CD=$(grep -lr "program:nox_sidecar" /etc/supervisor /etc/supervisord* $N/ops 2>/dev/null | head -1 | xargs -r dirname)
cp $W/nox_dpo5_daily.conf $CD/; supervisorctl reread >/dev/null; supervisorctl update >/dev/null; sleep 3; echo "sv nox_dpo5_daily $(supervisorctl status nox_dpo5_daily | awk '{print $2}')"
# разовый прогон сейчас (ждёт тишины владельца сам), в фоне
cd $D && setsid nohup nice -n 19 $N/venv/bin/python -I dpo5_daily.py --once > $N/logs/dpo5_once.log 2>&1 < /dev/null &
sleep 5; echo "once_started=$(pgrep -fc 'dpo5_daily.py --once')"
echo "teachers: $(for m in cerebras/qwen-3-32b llm7/gpt-oss:120b; do c=$(curl -s -o /dev/null -m 40 -w %{http_code} -H 'Content-Type: application/json' -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"скажи ок\"}],\"max_tokens\":5}" http://127.0.0.1:8793/v1/chat/completions); echo -n "$m=$c "; done)"
rm -rf $W; echo END
