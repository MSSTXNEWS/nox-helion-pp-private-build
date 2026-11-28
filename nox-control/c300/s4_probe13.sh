N=/workspace/nox
echo "S4P13 $(date +%F_%H:%M)"
sed -n 1,9p $N/mods/weekly_exam.py | cut -c1-250; sed -n 11,60p $N/mods/weekly_exam.py | cut -c1-250
echo "## stop check in exam"; grep -n "stop" $N/mods/weekly_exam.py | sed -n 5,25p | cut -c1-250
echo "## lib.py"; sed -n 20,30p $N/agent/nox_agents/lib.py | cut -c1-200; sed -n 80,90p $N/agent/nox_agents/lib.py | cut -c1-200; sed -n 140,160p $N/agent/nox_agents/lib.py | cut -c1-200
echo "## runners honoring stopped()"; grep -l "stopped()" $N/agent/nox_agents/*.py | wc -l; ls $N/agent/nox_agents/*.py | wc -l
echo "## last exam stop"; python3 -I -c "
import json;d=json.load(open('$N/state/core/weekly_exam.json'));print({k:v for k,v in d.items() if 'stop' in str(k).lower() or 'stop' in str(v).lower()[:300]})" 2>&1 | cut -c1-400
