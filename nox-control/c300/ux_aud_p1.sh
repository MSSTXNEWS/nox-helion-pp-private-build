echo "C300: ux_aud_p1"
O=/workspace/nox/agent/out; pgrep -f "qa_audit|u_audit5" | head -3
cat > $O/ux_aud_p1.sh <<'AEOF'
O=/workspace/nox/agent/out
while pgrep -f u_audit5.sh >/dev/null; do sleep 30; done
for p in system widgets memory map cinema knowledge; do
  flock /tmp/qaa.lock /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html > $O/ux_qa_$p.out 2>&1
  python3 - $p <<'PY' >> $O/ux_qa_prog.txt
import json,sys
d=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8')).get(sys.argv[1],{})
print(sys.argv[1],d.get('ts'),'U',d.get('U'),'ARU',d.get('ARU'),'axes',{k:v for k,v in d.items() if k in('wow','U','A','R')},'fails',[f.get('item','')[:30] for f in d.get('fails',[])][:4])
PY
done; echo FIN >> $O/ux_qa_prog.txt
AEOF
rm -f $O/ux_qa_prog.txt; setsid nohup bash $O/ux_aud_p1.sh >/dev/null 2>&1 </dev/null &
sleep 1; echo started
