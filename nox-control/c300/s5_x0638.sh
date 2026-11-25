echo "OUT: $(grep -a ' WOW ' /tmp/s5_chain2.log | cut -c1-45 | tr '\n' ';') $(tail -c 60 /tmp/s5_chain2.log | tr '\n' ' ')"
python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('settings','atlas','photo','chat','index'):
    v=a.get(k,{}); print('OUT: ST',k,v.get('status'),v.get('wow'),v.get('ARU'),v.get('ts','')[11:16],'vend',v.get('vendor_used'),[(f['item'][:22],str(f['detail'])[:60]) for f in v.get('fails',[])][:5])
P
ls /workspace/nox/web/site/qa/rework/*.fixed 2>/dev/null | xargs -n1 basename | tr '\n' ' ' | sed 's/^/OUT: fixed /'; date +%H:%M
