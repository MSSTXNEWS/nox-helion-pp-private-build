echo "C300: a2_collect4"
A=/workspace/nox/agents
echo "== eval"; tail -3 $A/eval_llm.log | cut -c1-300; grep -E "^BAD|^ERR" $A/eval_llm.log | cut -c1-160
echo "== cons normal"; python3 -c "
import json;d=json.load(open('$A/cons_n.json'));print('sec',d['seconds'],'senior',d.get('senior'),'avail',d['advisors_available'],'err',d.get('errors'));[print(' w',w['wave'],[(o['advisor'],o['text'][:50]) for o in w['opinions']]) for w in d['waves']];print('FINAL',d['final'][:350])" 2>&1 | head -12
echo "== cons deep"; python3 -c "
import json;d=json.load(open('$A/cons_d.json'));print('sec',d['seconds'],'senior',d.get('senior'),'waves',[(w['wave'],len(w['opinions'])) for w in d['waves']],'err',d.get('errors'));print('FINAL',d['final'][:300])" 2>&1 | head -8
echo "== worms"; sed -n '/SCAN/,$p' $A/worms_live.log | cut -c1-300
echo "== receipt"; curl -s -m10 127.0.0.1:8810/task/1125-1e94af/receipt | head -c 700; echo
