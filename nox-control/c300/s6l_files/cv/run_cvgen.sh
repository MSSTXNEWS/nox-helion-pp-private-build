#!/bin/bash
# GPU-очередь (поток 6): генерация control vectors human_voice / ai_mind_voice. Запускать ТОЛЬКО в своё окно очереди и с захваченным BODY_LOCK; чат первый, VRAM <=92%.
# Использование: run_cvgen.sh MODEL.gguf   (по умолчанию модель тела; для MoE сначала проверка на малой, канон 27.4: «проверка на MoE обязательна перед включением»)
N=/workspace/nox; D=$N/state/cvectors; mkdir -p $D
M=${1:-$(ls $N/models/body/*/*/*.gguf 2>/dev/null | head -1)}
BIN=$(find $N -name llama-cvector-generator -type f 2>/dev/null | head -1)
[ -x "$BIN" ] || { echo "no cvector-generator binary"; exit 1; }
[ -f "$M" ] || { echo "no model"; exit 1; }
RAW=${RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/s6l_files/cv}
for f in cv_human.txt cv_ai.txt; do curl -fsSL --retry 3 $RAW/$f -o $D/$f || exit 1; done
echo "pairs: $(wc -l < $D/cv_human.txt) / $(wc -l < $D/cv_ai.txt)"
# human_voice: positive = человеческая речь, negative = речь разума ИИ
$BIN -m "$M" --positive-file $D/cv_human.txt --negative-file $D/cv_ai.txt -o $D/human_voice.gguf --pca-iter 500 -ngl 99 -c 512 -t 8 2>&1 | tail -3
# ai_mind_voice: наоборот
$BIN -m "$M" --positive-file $D/cv_ai.txt --negative-file $D/cv_human.txt -o $D/ai_mind_voice.gguf --pca-iter 500 -ngl 99 -c 512 -t 8 2>&1 | tail -3
ls -la $D/*.gguf | awk '{print $5,$9}'
echo "Применение: llama-server ... --control-vector-scaled $D/human_voice.gguf 0.2..0.6 (по одному за раз); проверка по cv_eval.jsonl и persona_exam часть C (0 клише)."
