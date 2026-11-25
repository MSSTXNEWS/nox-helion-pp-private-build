N=/workspace/nox; M=$N/models/flux; mkdir -p $M
echo "== t5/clip files"; find $N/models $N/agent /workspace -maxdepth 6 \( -iname "*t5*" -o -iname "clip_l*" -o -iname "*zimage*" \) -not -path "*/venv*" -not -path "*/site-packages/*" -not -path "*/build/*" -not -path "*/runtime/*" 2>/dev/null | head -10 | while read f; do echo "$(du -h "$f" 2>/dev/null | cut -f1) $f"; done
echo "== imgsvc code"; f=$(ls $N/agent/imgsvc*.py $N/agent/img*.py 2>/dev/null | head -2); echo "$f"; grep -n -E "t5|clip|ae\.safe|sd_binary|--diffusion|subprocess|cmd" $f | cut -c1-210 | head -25
echo "== hf_hub / token"; $N/venv/bin/python -c "import huggingface_hub;print(huggingface_hub.__version__)"; ls ~/.cache/huggingface/token 2>&1 | head -1
echo "== start downloads in background"
cat > $M/dl.sh <<'EOD'
#!/bin/bash
M=/workspace/nox/models/flux; cd $M
get(){ [ -s "$2" ] && return; curl -L -C - --retry 5 --retry-delay 5 -s -o "$2.part" "$1" && mv "$2.part" "$2" && echo "ok $2 $(du -h $2|cut -f1)"; }
get https://huggingface.co/leejet/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-q4_0.gguf flux1-schnell-q4_0.gguf
get https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors clip_l.safetensors
get https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors t5xxl_fp16.safetensors
cp -n /workspace/nox/models/first/silveroxides/Chroma1-HD-GGUF/ae.safetensors ae.safetensors && echo "ae copied (flux VAE, same as FLUX.1 ae)"
/workspace/nox/venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
for r in ("Falconsai/nsfw_image_detection","nateraw/vit-age-classifier"):
    try: print("dl",r,snapshot_download(r,local_dir="/workspace/nox/models/flux/"+r.split("/")[1]))
    except Exception as e: print("FAIL",r,type(e).__name__,str(e)[:150])
PY
echo ALLDONE
EOD
chmod +x $M/dl.sh; pgrep -f flux/dl.sh >/dev/null || { nohup setsid $M/dl.sh > $M/dl.log 2>&1 & echo started; }
