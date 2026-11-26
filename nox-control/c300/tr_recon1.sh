echo "C300: tr_recon1"
date -u; df -h /workspace | tail -1; uptime
cd /workspace/nox
echo "== autotrain files"; ls -la agent/autotrain/ | head -30; wc -l agent/autotrain/autotrain.sh distill_v2/distill_v2.py 2>&1
echo "== ops/dpo"; ls -la ops/dpo | head -60
echo "== gates dir"; ls -t distill_v2/gates | head -15
echo "== ckpt_keep"; ls -td distill_v2/ckpt_keep/* | head -8
echo "== state"; ls state | head -80
echo "== rounds"; ls -t agent/autotrain/rounds | head -4; ps aux | grep -E "autotrain|distill_v2|dpo" | grep -v grep | awk '{print $2,$11,$12,$13,$14}' | head
echo "== ext_cases"; find . -maxdepth 4 -iname "*ext_case*" 2>/dev/null | head
echo END
