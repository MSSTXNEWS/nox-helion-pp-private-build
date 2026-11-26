echo "C300: srv_k21"
cd /workspace/nox
python3 - <<'PY'
import json
r=json.loads(open('distill_v2/raw_skill_p3_antisyc_001.jsonl').readline()); print({k:(str(v)[:150]) for k,v in r.items()})
d=json.load(open('state/p3/persona_gen3.json')); print(type(d).__name__, (list(d)[:8] if isinstance(d,dict) else len(d)))
x=d if isinstance(d,list) else d.get('rows') or d
print(str(x)[:700])
import glob
f=glob.glob('distill_v2/gates/426f90c1ed069091-eval-*.json')[0]; e=json.load(open(f))
print(json.dumps(e['failures']['fidelity'][:2],ensure_ascii=False)[:700]); print(e['eval_suite'])
a=json.load(open('distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724/adapter_config.json')); print(a.get('base_model_name_or_path'),a.get('r'),a.get('target_modules'))
PY
ls distill_v2/gates | grep -v "eval-" | head -3
python3 - <<'PY'
import json,glob
f=[x for x in glob.glob('/workspace/nox/distill_v2/gates/*.json') if 'eval-' not in x][0]; d=json.load(open(f)); print(f[-40:], type(d).__name__, list(d)[:12] if isinstance(d,dict) else len(d))
PY
ls ops | grep -i -E "fid|faith|persona" | head; ls ops/p3_* 2>/dev/null | head
wc -l distill_v2/rows_train.jsonl; grep -c persona distill_v2/rows_train.jsonl
