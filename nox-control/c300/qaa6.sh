tail -3 /workspace/nox/web/site/qa/history.log
tail -5 /workspace/nox/agent/out/qa_audit.log
python3 -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k,v in d.items(): print('##',k,v['status'],'WOW',v.get('wow'));[print('  -',f['item'][:38],'|',str(f.get('detail'))[:220]) for f in v['fails']];print('  FIX',str(v.get('fix'))[:600]) ;print('  RAW',v.get('vision_raw','')[:120] if v.get('wow') is None else '')
" 2>&1 | cut -c1-900
