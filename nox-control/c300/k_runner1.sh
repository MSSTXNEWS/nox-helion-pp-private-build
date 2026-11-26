echo "C300: k_runner1"
IFS= read -r TOK
[ -n "$TOK" ] || { echo "no token on stdin"; exit 1; }
B=/workspace/nox/runners; mkdir -p $B; cd $B
V=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["tag_name"].lstrip("v"))')
echo "runner version $V"
[ -f actions-runner-$V.tgz ] || curl -fsSL -o actions-runner-$V.tgz https://github.com/actions/runner/releases/download/v$V/actions-runner-linux-x64-$V.tar.gz
export RUNNER_ALLOW_RUNASROOT=1
CONF=/etc/supervisor/conf.d/nox_runners.conf; : > $CONF.new
for i in $(seq -w 1 10); do
  D=$B/r$i
  if [ ! -f $D/.runner ]; then
    mkdir -p $D && tar xzf actions-runner-$V.tgz -C $D
    (cd $D && ./config.sh --unattended --url https://github.com/MSSTXNEWS/nox-helion-pp-private-build --token "$TOK" --name k1-r$i --labels k1 --work _work --replace >/dev/null 2>&1) && echo "r$i configured" || echo "r$i CONFIG FAILED"
  else echo "r$i already configured"; fi
  cat >> $CONF.new <<C
[program:nox_runner_r$i]
command=$D/run.sh
directory=$D
environment=RUNNER_ALLOW_RUNASROOT="1"
autostart=true
autorestart=true
priority=900
nice=10
stdout_logfile=$D/runner.log
stderr_logfile=$D/runner.log
C
done
mv $CONF.new $CONF
unset TOK
supervisorctl reread >/dev/null; supervisorctl update >/dev/null
sleep 15; supervisorctl status | grep nox_runner | awk '{print $1,$2}'
du -sh $B | cut -f1; df -h /workspace | tail -1
