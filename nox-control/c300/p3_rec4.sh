N=/workspace/nox
echo "== hunger refs"; grep -rIl --include=*.py --include=*.json --include=*.js -i -E "голод|hunger" $N/svc $N/agent $N/web/pkg/server $N/state/*.json $N/brain 2>/dev/null | grep -v -E "\.bak|/backup/" | head -8
f=$(grep -rIl --include=*.py -i -E "hunger|голод" $N/svc $N/agent 2>/dev/null | grep -v bak | head -1); grep -n -i -E "hunger|голод" $f | head -8 | cut -c1-200
echo "== train status sources"; ls -t $N/distill_v2/train_logs | head -3; ls $N/state/*train* $N/state/arbiter.json 2>/dev/null; python3 -c "
import json;d=json.load(open('$N/state/arbiter.json'));print({k:str(v)[:80] for k,v in list(d.items())[:12]})"
tail -n 3 $(ls -t $N/distill_v2/train_logs/*.log 2>/dev/null | head -1) | cut -c1-220
echo "== existing status endpoints"; grep -n -E '"/api/(train|hunger|status|system)|/train/|/hunger' $N/web/pkg/server/web_server.py | head -12 | cut -c1-170
echo "== system page"; ls $N/web/site | grep -i -E "system|sys" | head; ls $N/web/site/vendor 2>/dev/null | grep -i echarts | head -3
echo "== privacy filter at 8793"; grep -n -E "personal_terms|allow_personal|def sanitize|redact" $N/advisors/gateway.py | head -10 | cut -c1-200; cat $N/advisors/*.json 2>/dev/null | head -c 600; ls $N/advisors | head -20; grep -n -i -E "иск|суд|финанс|здоров" $N/advisors/gateway.py | head -5 | cut -c1-200
echo "== training data from claude/NC excluded?"; grep -n -i -E "claude|nc_|source.*exclude|exclude_src|deny_src" $N/distill_v2/code/distill_v2.py | head -8 | cut -c1-170
echo "== dl"; ls -la $N/models/flux | cut -c20-120
