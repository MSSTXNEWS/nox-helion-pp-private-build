echo "C300: srv_k100"
cd /workspace/nox
grep -rIn "korea_img_disabled" --include=*.py --include=*.sh --include=*.json --include=*.conf . 2>/dev/null | grep -v "\.bak" | cut -c1-240 | head -12
echo "--- state"; ls state | grep -i -E "korea|img|draw" | head; cat state/draw_hold_s 2>/dev/null
echo "--- backups"
find /workspace /workspace/nox /workspace/nox/ops /workspace/nox/state -maxdepth 2 \( -name "*.bak*" -o -name "*backup*" -o -name "*.tar.gz" -o -name "*.tgz" \) -not -path "*nox-backup*" -not -path "*nox_mem*" -not -path "*restic*" -printf "%s %TY-%Tm-%Td %p\n" 2>/dev/null | sort -rn | head -25 | awk '{printf "%.2fGB %s %s\n",$1/1e9,$2,$3}'
echo "--- pipeline"
f=$(find /workspace/nox -maxdepth 3 -name pipeline_svc.py | head -1); echo $f; wc -l $f; grep -n "^def \|^async def \|K8meta\|^@app\|add_url_rule" $f | cut -c1-140 | head -40
ls models/gpu/protectai/* | head; nproc
