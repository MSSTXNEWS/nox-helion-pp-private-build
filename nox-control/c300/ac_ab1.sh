echo "C300: ac_ab1"
D=/workspace/nox/tmp/ab; mkdir -p $D
curl -sL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/chat_bench.py -o $D/cb.py
cat > $D/ab.sh <<'AB'
#!/bin/bash
D=/workspace/nox/tmp/ab; B=/workspace/nox/bin/llama-server
M=/workspace/nox/models/body/unsloth/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
BASE="--host 127.0.0.1 --port 8190 -m $M -ngl 99 -ot exps=CPU -c 4096 --parallel 1 -fa on -ctk q8_0 -ctv q8_0 --jinja"
run(){ name=$1; shift
  s=$(curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;print(sum(x['is_processing'] for x in json.load(sys.stdin)))")
  [ "$s" != "0" ] && { echo "$name SKIP chat busy" >> $D/res.txt; return; }
  setsid nohup nice -n 19 taskset -c 8-15,24-31 $B $BASE "$@" > $D/$name.log 2>&1 < /dev/null & pid=$!
  for i in $(seq 1 60); do curl -s -m2 127.0.0.1:8190/health | grep -q ok && break; sleep 3; done
  python3 $D/cb.py > $D/$name.out 2>&1; python3 $D/cb.py >> $D/$name.out 2>&1
  echo "$name: $(tail -1 $D/$name.out | cut -c1-90)" >> $D/res.txt
  kill $pid; sleep 6; pkill -f "port 8190"; sleep 2; }
: > $D/res.txt
run base -t 8
run ngram_simple -t 8 --spec-type ngram-simple
run ngram_mod -t 8 --spec-type ngram-mod --spec-ngram-mod-n-min 8 --spec-ngram-mod-n-max 32 --spec-ngram-mod-n-match 8
run ub1024 -t 8 -b 2048 -ub 1024
run t6 -t 6
run t12 -t 12
echo DONE >> $D/res.txt
AB
chmod +x $D/ab.sh; setsid -f bash $D/ab.sh </dev/null >$D/ab.log 2>&1
sleep 250; cat $D/res.txt; nvidia-smi --query-gpu=memory.used --format=csv,noheader
