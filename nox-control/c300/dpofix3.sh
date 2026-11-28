echo "K1: dpofix3"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo; L=$(readlink -f $D/char_cycle.lock); ino=$(stat -c %i $L)
echo "id=$(id -u) lock_ino=$ino"
for p in /proc/[0-9]*; do for f in $p/fd/*; do [ "$(stat -L -c %i $f 2>/dev/null)" = "$ino" ] && echo "holder $(basename $p) fd=$(basename $f) ppid=$(awk '{print $4}' $p/stat 2>/dev/null) etimes=$(ps -o etimes= -p $(basename $p) | tr -d ' ') comm=$(cat $p/comm 2>/dev/null)"; done; done 2>/dev/null | sort -u | head -12
echo "locks: $(grep -c . /proc/locks) match=$(awk -v i=$ino '$0 ~ ":"i" "' /proc/locks | head -3 | tr '\n' ';')"
echo END
