export RUNNER_TRACKING_ID=""
echo "C300: tr_img2"
F=/workspace/nox/imgsvc/image_service.py; wc -l $F
grep -n -E "^def |^class |^async def |@app|disabled|TRAIN|train|SIGSTOP|nvidia|flux|FLUX|warm|safety" $F | cut -c1-160 | head -70
echo "#### 150-200"; sed -n 150,200p $F | cut -c1-220
ps -eo pid,etimes,args | grep -E "[i]mage_service|[i]mgsvc" | cut -c1-120
echo END
