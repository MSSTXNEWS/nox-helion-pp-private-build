M=/workspace/nox/models/flux; pkill -f flux/dl.sh; pkill -f "curl.*flux1-schnell"; sleep 1
cat > $M/dl2.sh <<'EOD'
#!/bin/bash
M=/workspace/nox/models/flux; cd $M
get(){ f=$2; [ -s "$f" ] && return 0; for i in $(seq 1 60); do curl -L -C - -s --speed-time 20 --speed-limit 300000 --connect-timeout 15 -o "$f.part" "$1" && { mv "$f.part" "$f"; echo "ok $f $(du -h $f|cut -f1)"; return 0; }; sleep 3; done; echo "FAIL $f"; }
get https://huggingface.co/leejet/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-q4_0.gguf flux1-schnell-q4_0.gguf
get https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors clip_l.safetensors
cp -n /workspace/nox/models/first/silveroxides/Chroma1-HD-GGUF/ae.safetensors ae.safetensors && echo "ae copied"
/workspace/nox/venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
for r,d in (("Falconsai/nsfw_image_detection","nsfw_image_detection"),("nateraw/vit-age-classifier","vit-age-classifier")):
    try: print("dl",r,snapshot_download(r,local_dir="/workspace/nox/models/flux/"+d))
    except Exception as e: print("FAIL",r,type(e).__name__,str(e)[:150])
PY
echo ALLDONE
EOD
chmod +x $M/dl2.sh; nohup setsid $M/dl2.sh > $M/dl2.log 2>&1 &
sleep 45; ls -la $M | cut -c20-120; cat $M/dl2.log
