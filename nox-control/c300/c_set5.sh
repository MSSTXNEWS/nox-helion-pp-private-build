echo "C300: c_set5"
python3 -c "import json;p='/workspace/nox/state/persona.json';d=json.load(open(p));d['living_engines']['race_s']=5;json.dump(d,open(p,'w'),ensure_ascii=False,indent=1);print(d['living_engines'])"
