echo "C300: n_setup_1"
cd /workspace/nox
avail=$(df -BG --output=avail /workspace | tail -1 | tr -dc 0-9); echo "free GB: $avail"
[ "$avail" -lt 8 ] && { echo "STOP: мало места"; exit 0; }
mkdir -p models/living svc/living/logs state/living
cat > svc/living/export_emo.py <<'P'
import torch, os
from transformers import AutoTokenizer, AutoModelForSequenceClassification
n="cointegrated/rubert-tiny2-cedr-emotion-detection"; out="/workspace/nox/models/living"
os.environ.setdefault("HF_HOME","/workspace/nox/hf_home")
tok=AutoTokenizer.from_pretrained(n); m=AutoModelForSequenceClassification.from_pretrained(n).eval()
tok.save_pretrained(out)
print(m.config.id2label)
d=tok("тест",return_tensors="pt",padding="max_length",max_length=16)
torch.onnx.export(m,(d["input_ids"],d["attention_mask"]),out+"/emo.onnx",input_names=["input_ids","attention_mask"],output_names=["logits"],
  dynamic_axes={"input_ids":{0:"b",1:"s"},"attention_mask":{0:"b",1:"s"},"logits":{0:"b"}},opset_version=17,dynamo=False)
print("exported")
P
nohup bash -c '
[ -x venv_living/bin/python ] || python3 -m venv venv_living
venv_living/bin/pip install -q --no-cache-dir onnxruntime tokenizers numpy apscheduler > svc/living/logs/pip.log 2>&1; echo pip_rc=$? >> svc/living/logs/pip.log
HF_HOME=/workspace/nox/hf_home venv/bin/python svc/living/export_emo.py > svc/living/logs/export.log 2>&1; echo export_rc=$? >> svc/living/logs/export.log
' >/dev/null 2>&1 &
for i in $(seq 1 50); do sleep 10; grep -q export_rc svc/living/logs/export.log 2>/dev/null && break; done
tail -3 svc/living/logs/pip.log; tail -5 svc/living/logs/export.log | cut -c1-300
du -sh models/living venv_living; ls -la models/living; df -BG /workspace | tail -1
