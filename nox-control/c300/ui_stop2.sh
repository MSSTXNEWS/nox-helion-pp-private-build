echo "C300: ui_stop2 (останов СВОЕГО цикла 268761 и оставшихся потомков цикла 198950)"
desc(){ local p=$1; echo $p; for c in $(pgrep -P $p); do desc $c; done; }
a=$(ps -o args= -p 268761 2>/dev/null); echo "$a" | grep -q "for p in system memory map knowledge widgets projects music news cinema mail calendar; do QA_FAST=1" && { for p in $(desc 268761 | tac); do ps -o pid=,args= -p $p | cut -c1-100; kill $p 2>/dev/null; done; } || echo "268761: не найден/не мой"
# оставшийся из моего цикла 198950: creative.html flock/python с ppid 1 и возрастом < 10 мин, запущенный после kill
for p in $(pgrep -f "qa_audit.py creative.html"); do e=$(ps -o etimes= -p $p); pp=$(ps -o ppid= -p $p | tr -d ' '); [ "$e" -lt 900 ] && [ "$pp" = 1 -o "$(ps -o args= -p $pp | grep -c 'QA_FAST=1')" -gt 0 ] && { echo "kill creative $p age=$e ppid=$pp"; kill $p 2>/dev/null; pkill -P $p 2>/dev/null; } ; done
sleep 3; echo "== left"; ps -eo pid,ppid,etimes,args | grep "[q]a_audit" | cut -c1-120
