# AUD3: read-only; numbers/names/bools only
N=/workspace/nox; S=$N/state/core; M=$N/state/mind; NOW=$(date +%s)
age(){ [ -e "$1" ] && echo $(( (NOW-$(stat -c %Y "$1"))/3600 ))h || echo none; }
CC=$N/web/pkg/server/chat_core.py
echo "AUD3 $(date +%F_%H:%M)"
echo "## ch1"
echo "systemctl=$(command -v systemctl >/dev/null && echo yes || echo no) pid1=$(ps -p 1 -o comm= 2>/dev/null) supervisor_progs=$(supervisorctl status 2>/dev/null | wc -l) running=$(supervisorctl status 2>/dev/null | grep -c RUNNING) not_running=$(supervisorctl status 2>/dev/null | grep -v RUNNING | awk '{print $1"="$2}' | tr '\n' ' ')"
echo "uptime_h=$(awk '{printf "%d",$1/3600}' /proc/uptime) nproc=$(nproc) ram_gb=$(awk '/MemTotal/{printf "%d",$2/1048576}' /proc/meminfo) ram_avail_gb=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo)"
df -BG --output=size,avail,pcent $N 2>/dev/null | tail -1
nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv,noheader 2>/dev/null | head -2
echo "oom_dmesg=$(dmesg 2>/dev/null | grep -c -i 'out of memory')"
echo "disk_guard.log age=$(age $N/canon/disk_guard.log) lines=$(wc -l < $N/canon/disk_guard.log 2>/dev/null) rotations=$(grep -c -i 'rotat' $N/canon/disk_guard.log 2>/dev/null)"
echo "soul_hourly_ok age=$(age $N/canon/soul_hourly_ok.json) drive_sync age=$(age $N/canon/drive_sync.json)"
find $N /workspace -maxdepth 3 \( -iname "*soul*ark*" -o -iname "*soul*backup*" -o -iname "*.age" -o -iname "soul_*" \) -not -path "*/venv*" -not -path "*/build/*" 2>/dev/null | head -12 | while read f; do echo "bk $f size=$(stat -c %s "$f") age=$(age "$f")"; done
echo "restore_test files: $(find $N -maxdepth 3 -name 'restore_test*' -not -path '*/venv*' 2>/dev/null | wc -l) last_state: $(ls -t $N/state/*restore* $S/*restore* 2>/dev/null | head -1 | while read f; do echo "$(basename $f) $(age $f)"; done)"
echo "gb10_final dir: $([ -d $N/archive/gb10_final ] && echo yes size_mb=$(du -sm $N/archive/gb10_final 2>/dev/null | cut -f1) || echo no); gb10_judge_tunnel.off=$([ -e $N/state/gb10_judge_tunnel.off ] && echo 1 || echo 0)"
echo "## ch2"
ps -eo args 2>/dev/null | grep -E "llama-server" | grep -v grep | while read l; do echo "llama: $(echo "$l" | grep -o -E -- '--(parallel|ctx-size|n-parallel|slots|cache-prompt|control-vector[a-z-]*|slot-save-path|port|jinja|flash-attn|cache-type-[kv]|n-gpu-layers|np) *[^ ]*' | tr '\n' ' ')"; done | cut -c1-400
echo "redis=$(ss -ltn 2>/dev/null | grep -c ':6379 ') redis_proc=$(pgrep -c redis 2>/dev/null) arq_proc=$(pgrep -fc arq 2>/dev/null)"
echo "bus/board files: $(ls $N/state/*bus* $S/*bus* $N/state/bus* 2>/dev/null | wc -l) sqlite_wal=$(find $N/state -maxdepth 2 -name '*.sqlite3-wal' -o -maxdepth 2 -name '*.db-wal' 2>/dev/null | wc -l)"
echo "tasks by status:"; for f in $N/state/tasks/*.json; do python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('status'))" $f 2>/dev/null; done | sort | uniq -c | tr '\n' ' '; echo
echo "workspace.json slots (canon<=7)"; echo "dispatcher/hands modules: $(ls $N/agent/nox_agents/*.py 2>/dev/null | wc -l) agents; ops_core=$(supervisorctl status nox_ops_core 2>/dev/null | awk '{print $2}') runners=$(supervisorctl status 2>/dev/null | grep -c nox_runner)"
echo "ttft/speed logs:"; ls -la --time-style=+%m-%d_%H:%M $N/state/*speed* $N/state/*ttft* $S/*speed* $S/*ttft* 2>/dev/null | awk '{print $5,$6,$7}' | head
for f in $N/state/chat_speed*.json* $N/state/ttft*.json* ; do [ -f "$f" ] && python3 -I - "$f" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1])); print("speedfile",sys.argv[1].split("/")[-1],{k:v for k,v in d.items() if isinstance(v,(int,float))} if isinstance(d,dict) else len(d))
except Exception: pass
PY
done
echo "chat_core: filler=$(grep -c -i 'filler' $CC) status_from_board=$(grep -c -i 'доск\|board' $CC) effer=$(grep -c -i 'эфферент\|expect' $CC) dry=$(grep -c -i '\"dry_\|dry_multiplier\|min_p' $CC) time_in_turn=$(grep -c -E 'strftime\(.%H:%M|date\.today|datetime\.now' $CC) deadline=$(grep -c -i 'deadline' $CC)"
echo "## ch3"; echo "mode cmds in chat_core: $(grep -c -E 'режим разума|будь человеком|смешанн' $CC) ; dictionary lines = sensors 18/130"
echo "## ch7"
echo "life_loop ts age: $(age $M/life_loop.json); initiative.json age: $(age $M/initiative.json)"
echo "outbox files: $(ls $N/state/outbox* $S/outbox* $M/outbox* 2>/dev/null | wc -l) ; initiative msgs lines: $(cat $N/state/outbox*.jsonl $S/outbox*.jsonl 2>/dev/null | wc -l)"
echo "quiet-hours files modified (outbox) none-check; rituals age $(age $M/rituals.json)"
echo "silence_h from self_now (see AUD2); owner_active=$(supervisorctl status nox_owner_active 2>/dev/null | awk '{print $2}')"
echo "## ch9"
echo "worm files: $(find $N/agents $N/agent -maxdepth 2 -iname '*worm*' -not -name '*.pyc' 2>/dev/null | wc -l) supervisor worm progs: $(supervisorctl status 2>/dev/null | grep -ci worm)"
python3 -I - <<'PY'
import json,os,time,collections
S="/workspace/nox/state/core"; N="/workspace/nox"
def L(p):
    try: return json.load(open(p,encoding="utf-8"))
    except Exception: return None
h=L(S+"/hunt_requests.json")
if isinstance(h,dict):
    r=h.get("requests") or []
    print("hunt_requests n=%d"%len(r), "status:",dict(collections.Counter(str(x.get("status")) for x in r if isinstance(x,dict))), "keys",list(h.keys())[:8])
    if r and isinstance(r[0],dict): print("req keys",list(r[0].keys())[:12], "approved_flag_true=%d"%sum(1 for x in r if isinstance(x,dict) and (x.get("approved") is True or x.get("status") in("approved","absorbed"))))
else: print("hunt_requests absent")
for n in ("unknown_map","worm_goals"):
    d=L(S+"/%s.json"%n); print(n,("keys=%d"%len(d) if isinstance(d,(dict,list)) else "absent"),"age_h=%.0f"%((time.time()-os.path.getmtime(S+"/%s.json"%n))/3600) if os.path.exists(S+"/%s.json"%n) else "")
PY
find $N -maxdepth 3 \( -iname "*catalog*" -o -iname "*hunt*" -o -iname "absorb*" \) -not -path "*/venv*" -not -path "*/build/*" -not -path "*/web/*" -not -path "*/node_modules/*" 2>/dev/null | head -10 | while read f; do echo "cat $f size=$(stat -c %s "$f") lines=$(wc -l <"$f" 2>/dev/null) age=$(age "$f")"; done
echo "teachers/downloads dir: $(ls -d $N/models $N/teachers $N/hf_cache 2>/dev/null | tr '\n' ' ')"
echo "## ch10"
find $N \( -path "*/venv*" -o -path "*/build" -o -path "*/node_modules" -o -path "*/web" \) -prune -o -type f \( -iname "ready_bulk*" -o -iname "hold*.jsonl" -o -iname "*hold400*" -o -iname "*holdout*" \) -print 2>/dev/null | head -8 | while read f; do echo "ds $f lines=$(wc -l <"$f" 2>/dev/null) size=$(stat -c %s "$f") age=$(age "$f")"; done
echo "autotrain entries: $(ls $N/agent/autotrain | head -40 | tr '\n' ' ')" | cut -c1-600
echo "autotrain dirs by age (latest 5):"; ls -dt $N/agent/autotrain/*/ 2>/dev/null | head -5 | while read d; do echo "$(basename $d) $(age $d)"; done
echo "gates json count=$(ls $N/state/gates/*.json 2>/dev/null | wc -l) latest=$(ls -t $N/state/gates/*.json 2>/dev/null | head -1 | xargs -r basename) age=$(ls -t $N/state/gates/*.json 2>/dev/null | head -1 | while read f; do age $f; done)"
echo "train procs: $(ps -eo args | grep -E 'train|unsloth|sft|dpo' | grep -v grep | grep -c .)"; ps -eo etimes,args 2>/dev/null | grep -E "train_|unsloth|dpo" | grep -v grep | awk '{print "etime_h="int($1/3600), $2, $3}' | cut -c1-150 | head -4
echo "trainer flags in last train script: $(ls -t $N/agent/autotrain/*.py 2>/dev/null | head -1 | xargs -r basename)"
for k in max_steps num_train_epochs replay hold early_stop oom; do echo "  at[$k]=$(grep -l -i "$k" $N/agent/autotrain/*.py 2>/dev/null | wc -l)"; done
echo "dpo5_daily age: $(age $N/state/dpo5_daily.json) ; adapters (*.safetensors in autotrain): $(find $N/agent/autotrain -name 'adapter_model.safetensors' 2>/dev/null | wc -l)"
echo "## ch11"
echo "voice supervisor: $(supervisorctl status nox_voice 2>/dev/null | awk '{print $2}') ports:$(ss -ltn 2>/dev/null | grep -o -E ':(8600|8601|8602|8610|8700|8710|10200|8400|8401)\b' | sort -u | tr '\n' ' ')"
for k in "t-one\|tone" piper qwen3.tts "gigaam\|parakeet" pipecat silero "barge" "vad" "filler" "whisper" "cosyvoice"; do echo "  voice_service[$k]=$(grep -c -i "$k" $N/mods/voice_service.py 2>/dev/null) piper_tts[$k]=$(grep -c -i "$k" $N/mods/piper_tts.py 2>/dev/null)"; done
echo "voice models: $(find $N /workspace -maxdepth 4 \( -iname '*piper*.onnx' -o -iname '*t-one*' -o -iname '*tone*onnx*' -o -iname '*qwen3*tts*' -o -iname '*gigaam*' -o -iname '*silero*' \) -not -path '*/venv*' -not -path '*/build/*' 2>/dev/null | xargs -n1 basename 2>/dev/null | head -10 | tr '\n' ' ')"
find $N/state -maxdepth 2 -iname "*voice*" -type f 2>/dev/null | head -5 | while read f; do echo "vstate $(basename $f) size=$(stat -c %s $f) age=$(age $f)"; done
echo "## ch12"
echo "imgsvc :8500=$(ss -ltn 2>/dev/null | grep -c ':8500 ') sd-server proc=$(pgrep -fc 'sd-server') comfy=$(pgrep -fc -i comfy)"
echo "image models: $(find $N /workspace -maxdepth 4 -iname '*.gguf' \( -iname '*z-image*' -o -iname '*qwen-image*' -o -iname '*chroma*' -o -iname '*wan*' -o -iname '*ltx*' \) -not -path '*/build/*' 2>/dev/null | xargs -n1 basename 2>/dev/null | head -8 | tr '\n' ' ')"
echo "vision gguf: $(find $N /workspace -maxdepth 4 -iname '*VL*.gguf' -o -maxdepth 4 -iname '*mmproj*' 2>/dev/null | xargs -n1 basename 2>/dev/null | head -5 | tr '\n' ' ')"
echo "draw_selfeval.log lines=$(wc -l < $N/state/draw_selfeval.log 2>/dev/null) age=$(age $N/state/draw_selfeval.log) ; draw tool refs in chat_core=$(grep -c -i 'draw' $CC) ; sandbox_run=$(grep -c '_sandbox_run' $CC) docker=$(command -v docker >/dev/null && echo yes || echo no) openhands=$(find $N -maxdepth 3 -iname '*openhands*' -not -path '*/venv*' 2>/dev/null | wc -l)"
echo "video: $(supervisorctl status 2>/dev/null | grep -ci video) music=$(supervisorctl status nox_music 2>/dev/null | awk '{print $2}')"
echo "## ch13"
echo "stop in chat_core: $(grep -c -i 'stop' $CC) ; STOP file refs: $(grep -c -i 'state/stop\|STOP_FLAG\|stop.flag' $CC) ; STOP files now: $(ls $N/state/STOP* $N/state/stop* 2>/dev/null | wc -l)"
echo "autonomy_matrix: $(python3 -I -c "import json;d=json.load(open('$N/canon/autonomy_matrix.json'));print('keys',list(d.keys())[:10] if isinstance(d,dict) else len(d))" 2>/dev/null)"
echo "foreign-text marking in chat_core: $(grep -c -i 'чужой\|недоверенн\|untrusted\|инъекц\|inject' $CC) ; _CS_PRIV=$(grep -c '_CS_PRIV' $CC)"
find $N/state -maxdepth 2 -type f \( -iname "*inject*" -o -iname "*agentdojo*" -o -iname "*redteam*" -o -iname "*stop_test*" -o -iname "*stop_lat*" \) 2>/dev/null | head -6 | while read f; do echo "sec $(basename $f) size=$(stat -c %s $f) age=$(age $f)"; done
echo "guard svc=$(supervisorctl status nox_guard_svc 2>/dev/null | awk '{print $2}') immunity.jsonl age=$(age $M/immunity.jsonl)"
echo END
