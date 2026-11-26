echo "C300: k2_b1"
N=/workspace/nox; FD=$N/models/flux; SD=$N/bin/sd
T5=$N/models/first/city96/t5-v1_1-xxl-encoder-gguf/t5-v1_1-xxl-encoder-Q8_0.gguf
uptime; nvidia-smi --query-gpu=memory.used --format=csv,noheader; tail -1 $N/state/k2_dl.log
$SD --help 2>&1 | grep -E "diffusion-fa|offload|vae-tiling|clip-on-cpu|backend|--flow|circular|taesd" | cut -c1-150
P="a cat, highly detailed, vivid colors, sharp focus, professional composition, no watermark, no text"
run(){ n=$1; shift; s=$(date +%s.%N); timeout 170 "$@" > /tmp/sd_$n.log 2>&1; rc=$?; e=$(date +%s.%N); echo "VARIANT $n rc=$rc wall=$(echo "$e - $s" | bc)"; grep -E "completed in|sampling completed|decode_first|generate_image|total" /tmp/sd_$n.log | tail -4 | cut -c1-160; }
B="$SD --diffusion-model $FD/flux1-schnell-q4_0.gguf --vae $FD/ae.safetensors --clip_l $FD/clip_l.safetensors --t5xxl $T5 -p \"$P\" --cfg-scale 1.0 --sampling-method euler --steps 4 --seed 7"
run A_cur taskset -c 4-7,20-23 $SD --diffusion-model $FD/flux1-schnell-q4_0.gguf --vae $FD/ae.safetensors --clip_l $FD/clip_l.safetensors --t5xxl $T5 -p "$P" --cfg-scale 1.0 --sampling-method euler --steps 4 -W 1024 -H 1024 --seed 7 --backend te=cpu -t 6 -o /tmp/sdA.png
run B_te_cpu_768 taskset -c 4-7,20-23 $SD --diffusion-model $FD/flux1-schnell-q4_0.gguf --vae $FD/ae.safetensors --clip_l $FD/clip_l.safetensors --t5xxl $T5 -p "$P" --cfg-scale 1.0 --sampling-method euler --steps 4 -W 768 -H 768 --seed 7 --backend te=cpu -t 6 -o /tmp/sdB.png
run C_gpu_768 $SD --diffusion-model $FD/flux1-schnell-q4_0.gguf --vae $FD/ae.safetensors --clip_l $FD/clip_l.safetensors --t5xxl $T5 -p "$P" --cfg-scale 1.0 --sampling-method euler --steps 4 -W 768 -H 768 --seed 7 -t 8 -o /tmp/sdC.png
run D_gpu_768_fa $SD --diffusion-model $FD/flux1-schnell-q4_0.gguf --vae $FD/ae.safetensors --clip_l $FD/clip_l.safetensors --t5xxl $T5 -p "$P" --cfg-scale 1.0 --sampling-method euler --steps 4 -W 768 -H 768 --seed 7 -t 8 --diffusion-fa -o /tmp/sdD.png
run E_gpu_1024_fa $SD --diffusion-model $FD/flux1-schnell-q4_0.gguf --vae $FD/ae.safetensors --clip_l $FD/clip_l.safetensors --t5xxl $T5 -p "$P" --cfg-scale 1.0 --sampling-method euler --steps 4 -W 1024 -H 1024 --seed 7 -t 8 --diffusion-fa -o /tmp/sdE.png
echo "--- safety"; s=$(date +%s.%N); $N/venv/bin/python -I $N/ops/draw/safety_check.py /tmp/sdD.png 2>&1 | tail -1 | cut -c1-150; echo "safety wall=$(echo "$(date +%s.%N) - $s" | bc)"
echo "--- translate 8141"; s=$(date +%s.%N); curl -s -m 60 localhost:8141/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","messages":[{"role":"system","content":"Translate to a concise English image prompt. Output only it."},{"role":"user","content":"нарисуй кота"}],"max_tokens":60,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' | head -c 300; echo; echo "translate wall=$(echo "$(date +%s.%N) - $s" | bc)"
nvidia-smi --query-gpu=memory.used --format=csv,noheader
