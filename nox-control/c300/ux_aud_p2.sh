echo "C300: ux_aud_p2"
O=/workspace/nox/agent/out
cat > $O/ux_aud_p2.sh <<'AEOF'
O=/workspace/nox/agent/out
while pgrep -f ux_aud_p1.sh >/dev/null; do sleep 30; done
for p in projects pdf atlas; do
  flock /tmp/qaa.lock /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html > $O/ux_qa2_$p.out 2>&1
  python3 - $p <<'PY' >> $O/ux_qa2_prog.txt
import json,sys
d=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8')).get(sys.argv[1],{})
print(sys.argv[1],d.get('ts'),'wow',d.get('wow'),'ARU',d.get('ARU'),'fails',[f.get('item','')[:30] for f in d.get('fails',[])][:3])
PY
done; echo FIN >> $O/ux_qa2_prog.txt
AEOF
setsid nohup bash $O/ux_aud_p2.sh >/dev/null 2>&1 </dev/null &
sleep 1; echo started
