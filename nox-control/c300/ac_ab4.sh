echo "C300: ac_ab4"
D=/workspace/nox/tmp/ab
for i in $(seq 1 30); do grep -q DONE $D/res.txt && break; sleep 5; done; cat $D/res.txt | cut -c1-70
S=$(pgrep -f "llama-swap -config"); kill $S; sleep 3
cd /workspace/nox && setsid nohup /workspace/nox/bin/llama-swap -config /workspace/nox/serve/llama-swap.yaml -listen 127.0.0.1:8200 >/tmp/llama-swap.log 2>&1 </dev/null &
sleep 4; curl -s -m3 127.0.0.1:8200/running | head -c 100; echo; curl -s -m3 127.0.0.1:8200/v1/models | python3 -c "import sys,json;print([m['id'] for m in json.load(sys.stdin)['data']])" | cut -c1-400
sed -e 's/^run base -t 8$/run base -t 8; run ub1024 -t 8 -b 2048 -ub 1024; run base2 -t 8; run ub1024b -t 8 -b 2048 -ub 1024; run ngram_modb -t 8 --spec-type ngram-mod --spec-ngram-mod-n-min 8 --spec-ngram-mod-n-max 32 --spec-ngram-mod-n-match 8; echo DONE >> $D\/res.txt; exit/' $D/ab.sh > $D/ab2.sh; sed -i 's#^: > \$D/res.txt#: > $D/res.txt#' $D/ab2.sh
setsid -f bash $D/ab2.sh </dev/null >$D/ab2.log 2>&1
sleep 120; cat $D/res.txt | cut -c1-70
