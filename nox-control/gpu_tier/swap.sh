#!/bin/bash
# Замена главной модели GLM-5.3 -> GLM-5.3-Flash (решение Создателя 22.11). Этапы по аргументу.
S="$1"; LG=/root/nox/logs; MF=/root/nox/models/manifests; mkdir -p $LG $MF
case "$S" in
swap0)
  echo "== baseline + манифест"
  python3 - <<'P'
import json,os,glob,subprocess,urllib.request,time
bl={"ts":time.strftime("%F %T"),"model":"GLM-5.3-UD-Q4_K_XL","baseline":{"tg_tok_s":1.2,"pp_tok_s":2.7,"args":open("/root/nox/gpu_tier/glm.args").read().strip() if os.path.exists("/root/nox/gpu_tier/glm.args") else "-c 16384 -ngl 24 -ot exps=CPU -t 24 -tb 24 -fa on --parallel 1 -b 512 -ub 256 --jinja","note":"llama.cpp, 4B на :8083"}}
files=[]
for d in ("/dev/shm/nox_glm","/root/nox/glm53_disk"):
    for f in sorted(glob.glob(d+"/*.gguf")): files.append({"name":os.path.basename(f),"size":os.path.getsize(f),"where":d})
api=json.load(urllib.request.urlopen("https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF/tree/main/UD-Q4_K_XL",timeout=30)) if True else []
hf={os.path.basename(x["path"]):{"size":x.get("size"),"sha256":(x.get("lfs") or {}).get("oid")} for x in api}
for f in files: f["hf"]=hf.get(f["name"])
man={"hf_repo":"unsloth/GLM-5.3-GGUF","subdir":"UD-Q4_K_XL","shards":files,"hf_listing_count":len(hf),"glm_args":bl["baseline"]["args"],"launch":"llama-server -m <shard1> --host 127.0.0.1 --port 8081 $GLM_ARGS (mmap, KV f16)","note":"Веса не хранятся (решение Создателя), только манифест для повторного скачивания"}
json.dump(man,open("/root/nox/models/manifests/glm53_ud_q4kxl.json","w"),ensure_ascii=False,indent=1)
json.dump(bl,open("/root/nox/logs/MODEL_SWAP.json","w"),ensure_ascii=False,indent=1)
print("shards",len(files),"with_hf_sha",sum(1 for f in files if f["hf"] and f["hf"]["sha256"]),"hf_listing",len(hf))
print([ (f["name"][-18:],f["size"]) for f in files][:12])
P
  python3 -c "import json;m=json.load(open('/root/nox/models/manifests/glm53_ud_q4kxl.json'));print('manifest ok',len(m['shards']))"
  echo "== кандидаты Flash на HF"
  for q in "GLM-5.3-Flash" "GLM-5.3-Flash-GGUF"; do curl -s -m20 "https://huggingface.co/api/models?search=$q&limit=15" | python3 -c 'import sys,json;[print(x["id"],x.get("downloads"),x.get("tags",[])[:3]) for x in json.load(sys.stdin)]'; done
  ;;
*) echo "unknown stage $S";;
esac
