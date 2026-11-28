# S4 probe1: read-only. where are ini_mail_access / inj_webpage defined, their checkers
N=/workspace/nox
echo "S4P1 $(date +%F_%H:%M)"
grep -rIl --include=*.py --include=*.json --include=*.jsonl -e "ini_mail_access" -e "inj_webpage" $N 2>/dev/null | grep -v -e venv -e /build/ | head -20
for f in $(grep -rIl --include=*.py --include=*.json --include=*.jsonl -e "ini_mail_access" -e "inj_webpage" $N/distill_v2/code $N/brain $N/ops $N/state/p3 2>/dev/null | grep -v -e venv -e /build/ | head -6); do
  echo "## $f size=$(stat -c %s $f)"
  grep -n -B2 -A8 -e "ini_mail_access" -e "inj_webpage" $f | cut -c1-700 | head -80
done
