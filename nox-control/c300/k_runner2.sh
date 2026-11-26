echo "C300: k_runner2"
IFS= read -r TOK
[ -n "$TOK" ] || { echo "no token on stdin"; exit 1; }
B=/workspace/nox/runners; export RUNNER_ALLOW_RUNASROOT=1
cd $B/r01 && (./bin/installdependencies.sh >/tmp/rdeps.log 2>&1; echo "deps rc=$?"; tail -3 /tmp/rdeps.log)
cd $B/r01 && ./config.sh --unattended --url https://github.com/MSSTXNEWS/nox-helion-pp-private-build --token "$TOK" --name k1-r01 --labels k1 --work _work --replace 2>&1 | sed "s/$TOK/***/g" | tail -15
if [ -f $B/r01/.runner ]; then
  for i in $(seq -w 2 10); do (cd $B/r$i && ./config.sh --unattended --url https://github.com/MSSTXNEWS/nox-helion-pp-private-build --token "$TOK" --name k1-r$i --labels k1 --work _work --replace >/dev/null 2>&1) && echo "r$i ok" || echo "r$i FAIL"; done
fi
unset TOK
supervisorctl restart all_noop >/dev/null 2>&1; for i in $(seq -w 1 10); do supervisorctl restart nox_runner_r$i >/dev/null 2>&1; done
sleep 15; supervisorctl status | grep nox_runner | awk '{print $1,$2}'
