echo "C300: ui_stop1 (останов СВОИХ циклов QA_FAST: 198950 и 268761 и их потомков, по поручению координатора)"
desc(){ local p=$1; echo $p; for c in $(pgrep -P $p); do desc $c; done; }
for root in 198950 268761; do
  a=$(ps -o args= -p $root 2>/dev/null | cut -c1-100); echo "root $root: $a"
  echo "$a" | grep -q "QA_FAST=1 flock /tmp/qaa.lock" || { echo "  skip: не мой цикл"; continue; }
  for p in $(desc $root | tac); do ps -o pid=,args= -p $p | cut -c1-110; kill $p 2>/dev/null; done
done
sleep 3; echo "== left"; ps -eo pid,ppid,etimes,args | grep "[q]a_audit" | cut -c1-120
