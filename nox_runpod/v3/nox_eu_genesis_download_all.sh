#!/usr/bin/env bash
# NOX EU GENESIS: strict real-weights install on A40 cu1zrw3apt5zt0.
# New installation, not a restoration of prior NOX's lost private /opt checkpoint.
# Resumable, SHA256 verified, never invents a successful train or model transfer.
set -Eeuo pipefail
export HF_HUB_DISABLE_TELEMETRY=1
R=/workspace/nox
D=/opt/nox_eu_genesis
BASE="${NOX_SOURCE_ROOT:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110}"
mkdir -p "$R/models" "$R/teachers" "$R/dispatcher/nox_v3/bin" "$R/distillation" "$R/logs" "$R/memory/NOX_UNIFIED_S03" "$D"
exec 9>"$D/bootstrap.lock"
flock -n 9 || { echo HOLD_BOOTSTRAP_ALREADY_RUNNING;exit 2; }
exec > >(tee -a "$R/logs/NOX_EU_GENESIS_BOOTSTRAP.log") 2>&1
say(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
say BOOTSTRAP_BEGIN
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
findmnt /workspace || { say HOLD_STORAGE_NOT_MOUNTED;exit 3; }
df -h /workspace /opt
# Never fill root/container with heavy weights. Shared global volume at /workspace.
python3 -m venv --system-site-packages "$D/venv"
"$D/venv/bin/python" -m pip install -q -U 'huggingface_hub>=0.35' 'transformers>=4.57' accelerate safetensors sentencepiece
# Install a dedicated real GPU llama-server. Check CUDA SDK separately from runtime.
BINARY="$D/llama.cpp/build/bin/llama-server"
if [ ! -x "$BINARY" ];then
 export PATH="/usr/local/cuda-12.8/bin:/usr/local/cuda/bin:$PATH"
 if ! command -v nvcc >/dev/null 2>&1;then
  say INSTALLING_CUDA_COMPILER_NOT_DRIVER
  curl -fsSL --retry 3 https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/nox_cuda_keyring.deb
  dpkg -i /tmp/nox_cuda_keyring.deb
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends cuda-toolkit-12-8
 fi
 command -v nvcc || { say HOLD_CUDA_COMPILER;exit 4; }
 if [ ! -d "$D/llama.cpp/.git" ];then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$D/llama.cpp"
 fi
 cmake -S "$D/llama.cpp" -B "$D/llama.cpp/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86
 cmake --build "$D/llama.cpp/build" --target llama-server -j 3
fi
test -x "$BINARY" || { say HOLD_GPU_LLAMA_BINARY;exit 4; }
say CUDA_LLAMA_SERVER_READY
# Stage requested models in the shared volume with strong SHA provenance;
# inspect free bytes before each download, no duplicates and no silent CPU fallback.
cat >"$D/download_models.py" <<'PY'
import hashlib,json,os,pathlib,shutil,sys,time
from huggingface_hub import hf_hub_download,snapshot_download,model_info
R=pathlib.Path("/workspace/nox")
models=[
 ("Qwen3.5-9B","Qwen/Qwen3.5-9B",None,R/"models/NOX_9B_UNIFIED",21_000_000_000),
 ("Qwen3.5-9B","bartowski/Qwen_Qwen3.5-9B-GGUF","Qwen3.5-9B-Q4_K_M.gguf",R/"teachers/Qwen3.5-9B",8_000_000_000),
 ("Qwen3.5-27B","bartowski/Qwen_Qwen3.5-27B-GGUF","Qwen3.5-27B-Q4_K_M.gguf",R/"teachers/Qwen3.5-27B",20_000_000_000),
 ("DeepSeek-R1-Distill-Qwen-32B","bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF","DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf",R/"teachers/DeepSeek-R1-Distill-Qwen-32B",22_000_000_000)]
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
 return h.hexdigest()
def atom(path,obj):
 tmp=path.with_suffix(path.suffix+".tmp")
 with open(tmp,"w") as f:json.dump(obj,f,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
fail=[]
for name,repo,file,root,needed in models:
 root.mkdir(parents=True,exist_ok=True)
 proof=root/("nox_teacher_proof.json" if file else "NOX_UNIFIED_RECEIPT.json")
 if file and proof.exists():
  try:
   d=json.loads(proof.read_text());p=root/file
   if p.is_file() and d.get("sha256")==sha(p) and d.get("bytes")==p.stat().st_size:
    print("REUSE_SHA_VERIFIED",name,flush=True);continue
  except Exception:pass
 if not file and proof.exists():
  try:
   d=json.loads(proof.read_text())
   if d.get("source_repository")=="Qwen/Qwen3.5-9B" and all((root/x["file"]).is_file() and sha(root/x["file"])==x["sha256"] for x in d["shards"]):
    print("REUSE_SHA_VERIFIED",name,flush=True);continue
  except Exception:pass
 free=shutil.disk_usage(root).free
 # 8GB reserved for S03/other state; on a short disk NEVER download a partial full set.
 if free < needed+8_000_000_000:
  fail.append(f"HOLD_DISK_{name}_FREE={free}_NEEDED={needed+8_000_000_000}")
  print(fail[-1],flush=True);continue
 try:
  revision=model_info(repo).sha
  if file:
   p=pathlib.Path(hf_hub_download(repo_id=repo,filename=file,revision=revision,local_dir=root))
   atom(proof,{"teacher":name,"model_file":p.name,"source":repo,"revision":revision,
      "sha256":sha(p),"bytes":p.stat().st_size,"status":"SHA256_VERIFIED_SHARED"})
  else:
   snapshot_download(repo_id=repo,revision=revision,local_dir=root,
     allow_patterns=["*.safetensors","*.json","*.txt","*.model","*.tiktoken","*.jinja"])
   files=sorted(root.glob("*.safetensors"))
   if len(files)<4:raise RuntimeError("MISSING_FULL_9B_SHARDS")
   shards=[{"file":f.name,"sha256":sha(f),"size":f.stat().st_size} for f in files]
   # This is an ORIGINAL, verified donor genesis; not a recovered NOX student.
   atom(proof,{"source_repository":repo,"revision":revision,"status":"VERIFIED_DONOR_ORIGIN_NOT_PREVIOUS_NOX",
       "training_steps":0,"shards":shards,"model":"Qwen3.5-9B"})
  print("MODEL_SHA_VERIFIED",name,revision,flush=True)
 except Exception as e:
  print("HOLD_DOWNLOAD",name,type(e).__name__,str(e)[:350],flush=True)
  fail.append(name)
print("DOWNLOAD_SUMMARY",json.dumps(fail),flush=True)
sys.exit(0 if not fail else 3)
PY
# Unlike a fake PASS, partial model downloads remain resumable and are reported.
"$D/venv/bin/python" -u "$D/download_models.py" || say HOLD_PARTIAL_DOWNLOAD_CHECK_LOG
# Install own actual code; old binary paths are NOT assumed to exist.
for name in nox_teacher_server_batch.py nox_teacher_s03_import.py nox_teacher_improvement_journal.py nox_night_progress_report.py;do
 tmp="$D/$name.tmp"
 if curl -fsSL --retry 3 "$BASE/nox_runpod/v3/$name" -o "$tmp" && python3 -m py_compile "$tmp";then
  install -m 644 "$tmp" "$R/dispatcher/nox_v3/bin/$name"
 else
  say "HOLD_SCRIPT_DOWNLOAD $name"
 fi
done
curl -fsSL --retry 3 "$BASE/nox_runpod/stage0/a40_full_parameter_distill_cycle.py" -o "$D/trainer.py"
python3 -m py_compile "$D/trainer.py"
install -m 644 "$D/trainer.py" "$R/dispatcher/nox_v3/bin/a40_full_parameter_distill_cycle.py"
# Preserve fixed S03 schema for same importer. This is empty until real teacher text arrives.
"$D/venv/bin/python" - <<'PY'
import sqlite3,pathlib
p=pathlib.Path("/workspace/nox/memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3")
c=sqlite3.connect(p)
c.execute("""CREATE TABLE IF NOT EXISTS knowledge (
source_id TEXT PRIMARY KEY, content_sha TEXT, teacher TEXT, source_file TEXT,
content TEXT, topic TEXT, received_utc TEXT, created_utc TEXT, quality TEXT)""")
c.commit();c.close()
print("S03_SCHEMA_READY_NO_FAKE_TEACHER_DATA")
PY
# Launch the single-GPU sequential 3-teacher -> S03 -> all-parameter loop.
CYCLE="$D/nox_eu_genesis_cycle.py"
curl -fsSL --retry 3 "$BASE/nox_runpod/v3/nox_eu_genesis_cycle.py" -o "$CYCLE.new"
python3 -m py_compile "$CYCLE.new"
mv -f "$CYCLE.new" "$CYCLE"
if ! pgrep -f "^$D/venv/bin/python -u $CYCLE$" >/dev/null;then
 nohup "$D/venv/bin/python" -u "$CYCLE" >>"$R/logs/NOX_EU_GENESIS_ENGINE.log" 2>&1 </dev/null &
 say "GENESIS_CYCLE_STARTED_PID=$!"
else say GENESIS_CYCLE_ALREADY_RUNNING;fi
say BOOTSTRAP_DONE_MODELS_MUST_SHOW_SHA_VERIFIED_BEFORE_GPU_TRAINING
