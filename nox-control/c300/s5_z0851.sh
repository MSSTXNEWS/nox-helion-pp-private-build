df -BG /workspace | tail -1 | sed 's/^/OUT: df /'
du -sh /tmp/s5_* /workspace/nox/web/site/qa 2>/dev/null | tr '\n' ' ' | sed 's/^/OUT: du /'
python3 - <<'P'
import json,re
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
log=open('/tmp/s5_chain4.log',errors='ignore').read()
print("OUT: done",re.findall(r"DONE (\w+)",log))
for k in ('news','chat','photo'):
    v=a.get(k,{}); print("OUT:",k,v.get('status'),v.get('wow'),v.get('ARU'),v.get('ts','')[11:16],'load',[f['detail'] for f in v.get('fails',[]) if 'load' in str(f['detail'])],[(f['item'][:24],str(f['detail'])[:50]) for f in v.get('fails',[])][:5])
P
