echo "C300: n_setup_3"
cd /workspace/nox
SP=/workspace/nox/venv_living/lib/python3.10/site-packages; X=/tmp/n_onnx_path; rm -rf $X; mkdir -p $X
for d in google onnx ml_dtypes; do [ -e $SP/$d ] && ln -s $SP/$d $X/$d; done
sed -i '1d' svc/living/export_emo.py; sed -i '1i import sys; sys.path.insert(0,"/tmp/n_onnx_path")' svc/living/export_emo.py
head -2 svc/living/export_emo.py
HF_HOME=/workspace/nox/hf_home timeout 400 venv/bin/python svc/living/export_emo.py 2>&1 | tail -6 | cut -c1-300
ls -la models/living; du -sh venv_living
venv_living/bin/python - <<'P'
import onnxruntime as ort, numpy as np
from tokenizers import Tokenizer
t=Tokenizer.from_file("/workspace/nox/models/living/tokenizer.json")
s=ort.InferenceSession("/workspace/nox/models/living/emo.onnx",providers=["CPUExecutionProvider"])
for x in ["Мне очень грустно и одиноко","Ура, у меня всё получилось!","Меня бесит этот сервис","Привет, как дела"]:
    e=t.encode(x); ids=np.array([e.ids],dtype=np.int64); m=np.array([e.attention_mask],dtype=np.int64)
    l=s.run(None,{"input_ids":ids,"attention_mask":m})[0][0]; p=1/(1+np.exp(-l)); print(x,[round(float(v),2) for v in p])
P
df -BG /workspace | tail -1

