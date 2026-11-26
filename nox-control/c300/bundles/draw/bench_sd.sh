#!/usr/bin/env bash
# K1 26.11: A/B sd.cpp флагов для FLUX schnell q4_0 (1024x1024, 4 шага). ТОЛЬКО в окно тишины (GPU свободен >=12 ГБ, чат молчит).
# Результат: /workspace/nox/ops/draw/bench_sd.txt  (секунды на картинку: база vs --diffusion-fa vs +taesd-preview-only)
N=/workspace/nox; F=$N/models/flux; T5=$N/models/first/city96/t5-v1_1-xxl-encoder-gguf/t5-v1_1-xxl-encoder-Q8_0.gguf; O=$N/ops/draw/bench_sd.txt
[ -e $N/agent/LIVE_TURN ] && { echo "чат идёт" > $O; exit 1; }
FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "$FREE" -lt 13000 ] && { echo "мало VRAM $FREE" > $O; exit 2; }
base=(taskset -c 4-7,20-23 $N/bin/sd --diffusion-model $F/flux1-schnell-q4_0.gguf --vae $F/ae.safetensors --clip_l $F/clip_l.safetensors --t5xxl $T5 -p "a red fox in snow" --cfg-scale 1.0 --sampling-method euler --steps 4 -W 1024 -H 1024 --seed 7 --backend te=cpu -t 6)
: > $O
run(){ n=$1; shift; s=$(date +%s.%N); "${base[@]}" "$@" -o /tmp/bench_$n.png >/dev/null 2>/tmp/bench_$n.err; rc=$?; e=$(date +%s.%N); echo "$n rc=$rc sec=$(echo "$e - $s" | bc)" >> $O; }
run A_base; run A_base2; run B_fa --diffusion-fa; run B_fa2 --diffusion-fa
[ -s $F/taef1.safetensors ] && run C_fa_taesd_prev --diffusion-fa --preview tae --taesd $F/taef1.safetensors --taesd-preview-only --preview-path /tmp/bench_prev.png --preview-interval 1
cat $O
