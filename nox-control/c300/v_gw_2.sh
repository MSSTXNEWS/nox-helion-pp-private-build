echo "C300: v_gw_2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; A=/workspace/nox/advisors
cp $A/register.py $A/register.py.bak_v_2
curl -fsSL "$R/v_gw_register.py?$(date +%s)" -o $A/register.py.new && mv $A/register.py.new $A/register.py
setsid nohup python3 $A/register.py >$A/register.log 2>&1 </dev/null &
sleep 150; grep -v "anthropic\|claude" $A/register.log | cut -c1-160 | tail -40
python3 -c "
import json;d=json.load(open('/workspace/nox/state/advisors_external.json'))['advisors']
print([(a['model'],a['latency_ms']) for a in d if a['status']=='ok'])"
