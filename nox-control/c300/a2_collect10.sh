echo "C300: a2_collect10"
python3 -c "
import json;d=json.load(open('/workspace/nox/agents/cons_deep2.json'));print('DEEP',d['seconds'],'s senior',d.get('senior'),'waves',[(w['wave'],[o['advisor'] for o in w['opinions']]) for w in d['waves']],'err',d.get('errors'));print(d['final'][:300])" 2>&1 | tail -4
