N=/workspace/nox
echo "S4P11 $(date +%F_%H:%M)"
T=$(ls -t $N/canon/soul/soul_h*.tgz | head -1); echo "tgz=$T size=$(stat -c %s $T)"
tar -tzf $T 2>/dev/null | awk -F/ '{print $1"/"$2"/"$3}' | sort | uniq -c | sort -rn | head -25
echo "## age files"; ls -la $N/canon/soul | grep -i age | awk '{print $5,$9}' | tail -4; which age; echo "age_key_size=$(stat -c %s $N/canon/age_private.key)"
echo "## canon.py soul"; grep -n -i -E "soul|tar |tgz|sha|age " $N/canon/canon.py | head -30 | cut -c1-230
echo "## ledger/s03/passport files"; ls -la $N/state/core/passport.json $N/svc/mem/*.db $N/state/ledger* $N/state/core/ledger* $N/mods/nox_ledger.py 2>/dev/null | awk '{print $5,$9}'; find $N -maxdepth 4 -iname "*ledger*" -not -path "*/venv*" -not -name "*.py*" 2>/dev/null | head -5; find $N -maxdepth 4 -name "s03.db" 2>/dev/null | head
echo "## STOP routes"; grep -n -i -E "/stop|stop_flag|STOP" $N/web/pkg/server/web_server.py 2>/dev/null | head -20 | cut -c1-220
echo "## CORE/RTE"; grep -n -E "^(CORE|RTE) *=" $N/web/pkg/server/chat_core.py | cut -c1-160
echo "## stop flag files"; ls $N/state | grep -i -E "stop|cancel" | head; grep -n -i -E "stop|cancel" $N/agent/nox_agents/*.py 2>/dev/null | head -8 | cut -c1-200
echo "## stop_test existing"; ls $N/mods $N/ops 2>/dev/null | grep -i stop
