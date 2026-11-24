pgrep -af "qa_audit|qa_loop" | cut -c1-120
tail -12 /workspace/nox/agent/out/qa_audit.log
tail -2 /workspace/nox/web/site/qa/history.log
python3 -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k,v in d.items(): print(k,v['status'],'WOW',v.get('wow'),[f['item'][:40]+': '+str(f.get('detail'))[:140] for f in v['fails']],'FIX',v.get('fix'))
" 2>&1 | cut -c1-1500
