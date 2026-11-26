echo "C300: k_runner3"
IFS= read -r TOK
[ -n "$TOK" ] || { echo "no token on stdin"; exit 1; }
umask 077; T=/root/.k1rt; printf '%s' "$TOK" > $T; unset TOK
cat > /root/k1_runner_bg.sh <<'BG'
B=/workspace/nox/runners; L=$B/setup.log; export RUNNER_ALLOW_RUNASROOT=1
TOK=$(cat /root/.k1rt); echo "start $(date -u)" > $L
cd $B/r01 && ./bin/installdependencies.sh >>$L.deps 2>&1; echo "deps rc=$?" >> $L
for i in $(seq -w 1 10); do
  (cd $B/r$i && ./config.sh --unattended --url https://github.com/MSSTXNEWS/nox-helion-pp-private-build --token "$TOK" --name k1-r$i --labels k1 --work _work --replace 2>&1 | sed "s/$TOK/***/g" | tail -4 > $B/r$i/config.out)
  [ -f $B/r$i/.runner ] && echo "r$i ok" >> $L || { echo "r$i FAIL: $(tr '\n' ' ' < $B/r$i/config.out | cut -c1-300)" >> $L; }
done
rm -f /root/.k1rt; unset TOK
for i in $(seq -w 1 10); do supervisorctl restart nox_runner_r$i >/dev/null 2>&1; done
sleep 10; supervisorctl status | grep nox_runner | awk '{print $1,$2}' >> $L; echo DONE >> $L
BG
setsid -f bash /root/k1_runner_bg.sh </dev/null >/dev/null 2>&1
echo "launched bg"
