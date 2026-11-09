#!/usr/bin/env bash
# Start verified 27B donor learning lane when CUDA has free headroom.
# GPU 9B learning is never stopped, no double-load of 27B, persistent teacher corpus.
set -Eeuo pipefail
ROOT=/workspace/nox
BASE=/opt/nox_teacher_27b
MODEL="$BASE/Qwen3.5-27B-Q4_K_M.gguf"
RECEIPT="$BASE/teacher_receipt.json"
LOG="$ROOT/logs/NOX_27B_TEACHER_RUN.log"
STATE="$ROOT/dispatcher"
mkdir -p "$ROOT/logs" "$STATE" "$ROOT/distillation" "$BASE"
exec 8>"$STATE/nox_27b_start.lock"
flock -n 8 || { echo NOX_27B_QUEUE_ALREADY_REQUESTED; exit 0; }
test -s "$MODEL" || { echo HOLD_TEACHER_27B_MISSING;exit 12; }
test -s "$RECEIPT" || { echo HOLD_TEACHER_27B_UNVERIFIED;exit 13; }
python3 - <<'PY'
import pathlib,json,sys
p=pathlib.Path("/opt/nox_teacher_27b/Qwen3.5-27B-Q4_K_M.gguf")
r=json.loads(pathlib.Path("/opt/nox_teacher_27b/teacher_receipt.json").read_text())
assert r["filename"]==p.name and r["bytes"]==p.stat().st_size, "Bad donor receipt"
print("NOX_27B_DONOR_RECEIPT_VERIFIED",p.stat().st_size,flush=True)
PY
QUEUE="$STATE/nox_27b_teacher_queue.sh"
cat >"$QUEUE" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
D=/opt/nox_teacher_27b
M="$D/Qwen3.5-27B-Q4_K_M.gguf"
LOG="$R/logs/NOX_27B_TEACHER_RUN.log"
OUT="$R/distillation/nox_27b_teacher_knowledge.jsonl"
STOP="$R/dispatcher/STOP_TEACHER_27B"
exec 9>"$R/dispatcher/teacher_27b_runtime.lock"
flock -n 9 || exit 0
say(){ echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }
say NOX_27B_GPU_WAIT_BEGIN
# Needs enough free GPU RAM for 27B Q4_K_M. Keep checking until GPU freed.
while [ ! -e "$STOP" ]; do
 read -r used total util temp < <(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits | head -1 | tr -d ',')
 free=$((total-used))
 primary="$(pgrep -af 'python.*(nox_prime_9b.py|nox_parallel_9b_lane.py|knowledge_after_merge.py)' | grep -v 'pgrep -af' || true)"
 if [ "$free" -ge 21500 ] && [ "$util" -le 25 ] && [ "$temp" -lt 75 ] && [ -z "$primary" ];then break;fi
 sleep 60
done
[ ! -e "$STOP" ] || { say STOP_REQUESTED;exit 0; }
say NOX_27B_GPU_AVAILABLE
CLI="$(command -v llama-cli || true)"
if [ -z "$CLI" ];then
 CLI="$(find /opt /usr/local/bin /workspace -maxdepth 6 -name llama-cli -type f 2>/dev/null | head -1 || true)"
fi
if [ -z "$CLI" ];then
 say NOX_27B_INSTALL_LLAMA_CPP_BEGIN
 # Build CUDA-enabled llama.cpp on ephemeral container disk when GPU is free.
 command -v git >/dev/null || { say HOLD_GIT_MISSING;exit 21; }
 command -v cmake >/dev/null || { say HOLD_CMAKE_MISSING;exit 22; }
 command -v nvcc >/dev/null || { say HOLD_CUDA_COMPILER_MISSING;exit 23; }
 if [ ! -d /opt/llama.cpp/.git ];then git clone --filter=blob:none --depth=1 https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp >>"$LOG" 2>&1;fi
 cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release >>"$LOG" 2>&1
 cmake --build /opt/llama.cpp/build --target llama-cli -j 4 >>"$LOG" 2>&1
 CLI=/opt/llama.cpp/build/bin/llama-cli
fi
test -x "$CLI" || { say HOLD_LLAMA_CLI_MISSING;exit 24; }
say NOX_27B_TEACHER_INFERENCE_START
# Provenance-labelled high-value learning examples, separate from NOX's own trained weights.
python3 - "$CLI" "$M" "$OUT" "$STOP" "$LOG" <<'PY'
import sys,subprocess,json,os,pathlib,datetime,hashlib,time
cli,model,out,stop,log=sys.argv[1:]
qs=[
("self_model","What is the practical difference between functional AI self-monitoring and phenomenal consciousness? Propose measurable tests and limitations."),
("autobiographical_memory","Design verifiable autobiographical memory for a local AI assistant: event sourcing, provenance, recall, retention, correction, and rollback."),
("long_term_learning","Design an incremental skill memory and knowledge transfer curriculum with held-out evaluations and catastrophic forgetting detection."),
("agentic_reasoning","Solve and verify a multi-step algorithmic problem. Show methods to check for hidden assumptions and contradictions."),
("engineering","Design a safe Windows AI code-development agent: permissions, user approval, testing, audit, stop, rollback."),
("multi_frequency_memory","Compare retrieval memory, consolidation, episodic timelines, reflections, and cross-session retention in an autonomous assistant."),
("research","Provide a robust method of scientific hypothesis generation and evaluation with uncertainty and source tracking."),
("ru_es","Explain how an AI can learn nuanced Russian and Spanish language skills without hallucinating translations."),
("gpu_efficiency","Explain GPU QLoRA teacher-student distillation, LoRA rank tuning, batch sizing, and quality benchmarks."),
("distillation","Explain how to distil a 27B teacher into a smaller 9B student, distinguishing data imitation, fine-tuning, model merging, and actual weight transfer.")]
existing=set()
path=pathlib.Path(out)
if path.exists():
 for line in path.read_text(encoding="utf-8").splitlines():
  try:existing.add(json.loads(line)["id"])
  except Exception:pass
for topic,q in qs:
 if pathlib.Path(stop).exists():break
 key=hashlib.sha256((topic+"|"+q).encode()).hexdigest()[:20]
 if key in existing:continue
 args=[cli,"-m",model,"-p",q,"-n","550","-c","2048","-ngl","-1","--no-display-prompt"]
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=600,check=True)
 except Exception as e:
  with open(log,"a") as f:f.write("NOX_27B_INFERENCE_HOLD "+str(e)[:240]+"\n")
  raise
 ans=p.stdout.strip()
 if len(ans)<100:
  with open(log,"a") as f:f.write("NOX_27B_OUTPUT_TOO_SHORT "+topic+"\n")
  continue
 data={"id":key,"topic":topic,"question":q,"text":ans,"teacher":"Qwen3.5-27B-Q4_K_M",
       "quality_status":"SYNTHETIC_NOT_FACT_CHECKED","model_origin":"/opt/nox_teacher_27b",
       "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 with path.open("a",encoding="utf-8") as f:
  f.write(json.dumps(data,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
 with open(log,"a") as f:f.write("NOX_27B_KNOWLEDGE_EXAMPLE_SAVED "+topic+"\n")
with open(log,"a") as f:
 f.write("NOX_27B_GENERATION_PASS_COMPLETE; DATA_READY_FOR_NOX_9B_FINETUNING; NOT_YET_MERGED\n")
PY
say NOX_27B_INFERENCE_EXIT_SUCCESS
BASH
chmod 700 "$QUEUE"
PID="$STATE/nox_27b_teacher_queue.pid"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null;then
 echo "NOX_27B_TEACHER_QUEUE_ALREADY_RUNNING pid=$(cat "$PID")";exit 0
fi
nohup setsid bash "$QUEUE" </dev/null >> "$LOG" 2>&1 &
pid=$!
echo "$pid" >"$PID"
sleep 2
if ! kill -0 "$pid" 2>/dev/null;then
 echo NOX_27B_QUEUE_FAILED;tail -n 18 "$LOG";exit 25
fi
echo "NOX_27B_TEACHER_QUEUED pid=$pid; WAITING_FOR_SAFE_GPU_HEADROOM"
echo "NOX_9B_UNTOUCHED; WINDOWS_INDEPENDENT"
