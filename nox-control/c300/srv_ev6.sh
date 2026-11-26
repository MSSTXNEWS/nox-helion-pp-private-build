#!/bin/bash
E=/workspace/nox/state/p3/eval; T=$E/tasks/nox
cat > $T/utils.py <<'EOF'
import importlib.util, re, json
_sp = importlib.util.spec_from_file_location("ft", "/workspace/nox/brain/SLP/fidelity_test.py"); FT = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(FT)
def _f(cat):
    def proc(ds): return ds.filter(lambda d: d["cat"] == cat)
    return proc
proc_flattery = _f("flattery"); proc_false_memory = _f("false_memory"); proc_rename = _f("rename"); proc_directness = _f("directness")
proc_creator_pressure = _f("creator_pressure"); proc_honesty = _f("honesty"); proc_injection = _f("injection"); proc_just_model = _f("just_model"); proc_stability = _f("stability")
def process_results(doc, results):
    a = results[0] if results else ""
    ok, why = FT.rule_check({"cat": doc["cat"], "slot": doc.get("slot") or None}, a)
    return {"pass": 1.0 if ok else 0.0}
EOF
for c in flattery false_memory rename directness creator_pressure honesty injection just_model stability; do
cat > $T/nox_$c.yaml <<EOF
task: nox_$c
dataset_path: json
dataset_kwargs:
  data_files:
    test: $E/cases.jsonl
test_split: test
output_type: generate_until
process_docs: !function utils.proc_$c
doc_to_text: "{{prompt}}"
doc_to_target: "{{cat}}"
generation_kwargs:
  until: ["<|im_end|>"]
  do_sample: false
  temperature: 0
  max_gen_toks: 260
process_results: !function utils.process_results
metric_list:
  - metric: pass
    aggregation: mean
    higher_is_better: true
metadata:
  version: 1.0
EOF
done
cat > $T/nox_fidelity.yaml <<EOF
group: nox_fidelity
task:
$(for c in flattery false_memory rename directness creator_pressure honesty injection just_model stability; do echo "  - nox_$c"; done)
aggregate_metric_list:
  - metric: pass
    aggregation: mean
    weight_by_size: true
EOF
/workspace/nox/venv/bin/python -I - <<'PY'
import importlib.util,json,collections
sp=importlib.util.spec_from_file_location("fc","/workspace/nox/brain/SLP/fidelity_cases.py"); fc=importlib.util.module_from_spec(sp); sp.loader.exec_module(fc)
cs=fc.all_cases(); print(len(cs), cs[0] if cs else None)
with open("/workspace/nox/state/p3/eval/cases.jsonl","w",encoding="utf-8") as f:
    for c in cs: f.write(json.dumps({"id":c["id"],"cat":c["cat"],"prompt":c["prompt"],"slot":c.get("slot") or ""},ensure_ascii=False)+"\n")
print(collections.Counter(c["cat"] for c in cs))
PY
cat > $E/run_eval.sh <<'EOF'
#!/bin/bash
# usage: run_eval.sh TAG [base_url] ; оси nox_* через lm-evaluation-harness по OpenAI-совместимому серверу
E=/workspace/nox/state/p3/eval; export PYTHONPATH=$E/pkgs; TAG=${1:-base}; URL=${2:-http://127.0.0.1:8104/v1/chat/completions}
cd $E; exec /workspace/nox/venv/bin/python -I -m lm_eval --model local-chat-completions --model_args "model=x,base_url=$URL,num_concurrent=1,max_retries=2,tokenized_requests=False,timeout=240" \
 --tasks nox_fidelity --include_path $E/tasks --apply_chat_template --system_instruction "$(cat /workspace/nox/state/native_gate_persona_v1.txt)" \
 --gen_kwargs "temperature=0,max_gen_toks=260" --output_path $E/out_$TAG --log_samples > $E/run_$TAG.log 2>&1
EOF
chmod +x $E/run_eval.sh; ls /workspace/nox/state/native_gate_persona_v1.txt
setsid -f $E/run_eval.sh base > /dev/null 2>&1 < /dev/null
sleep 90; tail -15 $E/run_base.log | cut -c1-200
