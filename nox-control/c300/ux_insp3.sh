echo "C300: ux_insp3"
ps -o pid,etimes,stat,cmd -p $(pgrep -d, -f "qa_audit.py|ux_fast1") 2>&1 | cut -c1-140
O=/workspace/nox/agent/out; cat $O/ux_f_prog.txt 2>&1 | cut -c1-400; tail -c 600 $O/ux_f_system.out 2>&1
ls -la $O/ux_f_* 2>&1 | cut -c20-120
curl -s -m 5 localhost:8104/slots 2>&1 | head -c 500; echo
python3 -c "import json;print({k:v for k,v in json.load(open('/workspace/nox/state/advisors_cfg.json')).items() if k in('external_enabled','allow_external_images','allow_personal')})" 2>&1
