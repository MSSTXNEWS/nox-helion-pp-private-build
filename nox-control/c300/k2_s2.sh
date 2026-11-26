echo "C300: k2_s2"
N=/workspace/nox; ST=$N/state
P=$(ss -ltnp | grep ':8143 ' | grep -o 'pid=[0-9]*' | cut -d= -f2); echo "8143: $(ps -o pid,ppid,stat,rss,etimes -p $P | tail -1)"; PP=$(ps -o ppid= -p $P); ps -o pid,ppid,args -p $PP | tail -1 | cut -c1-160
python3 -c "
import json;r=json.load(open('$N/stewards/orch_registry.json'));js=r['jobs']
print([(j['name'],j.get('enabled')) for j in js if j['name'] in ('t_coder','t_q30','gen_coder')])"
grep -E "t_coder" $N/state/orch/orch.log | tail -4 | cut -c1-200
echo job2; cat $ST/k2_job2.log | cut -c1-300 | tail -6; echo job3; cat $ST/k2_job3.log 2>&1 | tail -8 | cut -c1-200; echo r8105; cat $ST/k2_r8105.log | cut -c1-200
