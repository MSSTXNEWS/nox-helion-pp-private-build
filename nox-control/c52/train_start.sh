#!/bin/bash
# c52: после перезапуска модели — обучение адаптера Qwen 9B на GPU0 новыми диалогами + пересборка знаний.
# Безопасно: STOP-флаг владельца уважается; без свободной VRAM не стартует; при ошибке модель/чат не трогаются.
L=/root/nox/logs/c52_train_start.log; exec >>$L 2>&1; echo "== $(date -Is) c52 train_start"
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && { echo "STOP flag $s -> skip"; exit 0; }; done
# ждём, пока модель и мост поднимутся (до 15 мин)
for i in $(seq 1 90); do curl -s -m3 127.0.0.1:8098/health | grep -q ok && curl -s -m3 127.0.0.1:8091/api/health >/dev/null && break; sleep 10; done
echo "model/bridge up after $((i*10))s"
# 1) знания: перезапуск эмбеддингов (были HTTP 500) и «сон» NOX (консолидация знаний в память)
supervisorctl restart nox-embed | tail -1; sleep 20
supervisorctl status nox-knowledge-index-t168u | grep -q RUNNING || supervisorctl start nox-knowledge-index-t168u
curl -s -m600 -X POST 127.0.0.1:8091/api/nox/sleep/run -H 'Content-Type: application/json' -d '{}' | head -c 400; echo
# 2) датасет: добавить новые диалоги владельца в корпус (без дублей)
D=/root/nox/state/qwen_corpus/6907283384; cp -a $D/train.jsonl $D/train.jsonl.bak_c52
/root/nox/venv/bin/python - <<'PY'
import json,hashlib
D="/root/nox/state/qwen_corpus/6907283384/train.jsonl"; seen=set()
for l in open(D,encoding="utf-8"):
    if l.strip(): seen.add(hashlib.sha256(json.dumps(json.loads(l)["messages"],ensure_ascii=False).encode()).hexdigest())
add=0
with open(D,"a",encoding="utf-8") as f:
    for src in ("/root/nox/state/turns.jsonl",):
        for l in open(src,encoding="utf-8"):
            try: t=json.loads(l)
            except Exception: continue
            u,a=str(t.get("u","")).strip(),str(t.get("a","")).strip()
            if len(u)<3 or len(a)<20 or "HOLD" in a[:20]: continue
            m=[{"role":"user","content":u},{"role":"assistant","content":a}]
            h=hashlib.sha256(json.dumps(m,ensure_ascii=False).encode()).hexdigest()
            if h in seen: continue
            seen.add(h); add+=1
            f.write(json.dumps({"messages":m,"provenance":{"channel":"owner_chat_turns","t":t.get("t"),"sha256":h}},ensure_ascii=False)+"\n")
print("added",add)
PY
# 3) обучение на GPU0 (схема владельца: GPU0 — обучение), только если хватает памяти
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0 | tr -d ' ')
echo "GPU0 free ${free}MiB"
if [ "${free:-0}" -lt 12000 ]; then echo "GPU0 мало памяти -> обучение не стартует (чат в приоритете)"; exit 0; fi
OUT=/root/nox/lora/qwen35_9b_t131u; sha256sum $D/train.jsonl | cut -c1-64 > $OUT/DATA_SHA
cd /root/nox/scripts && CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false PYTHONPATH=/root/nox/scripts \
 MICRO_BATCH=2 EFF_BATCH=8 MAX_STEPS=300 GPU_FRACTION=0.45 nohup nice -n 10 ionice -c2 -n7 /root/venv_volta/bin/python -u train_qwen35_9b_t131u.py >> /root/nox/logs/train_qwen9b_t131u.log 2>&1 &
echo "trainer pid $!"; sleep 60; tail -3 /root/nox/logs/train_qwen9b_t131u.log; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
