echo "C300: tr_fix3"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
date -u; rm -rf $N/models/guard_ru_eval; df -h /workspace | tail -1 | cut -c1-70; uptime
du -sm $N/distill_v2/ckpt_keep/* 2>/dev/null | sort -rn | head -4
curl -s -m5 localhost:8104/health | head -c 80; echo
H=$(curl -s -m5 localhost:8104/health | grep -c ok)
if [ "$H" = 1 ] && ! pgrep -f build_dpo3.py >/dev/null; then (cd $D && setsid -f nohup nice -n 8 $PY -I build_dpo3.py 110 >> $D/build3.log 2>&1 < /dev/null); sleep 3; echo "build3 запущен $(pgrep -f build_dpo3.py|head -1)"; else echo "донор не готов/уже идёт"; fi
grep -a -E "^[0-9:]{8} " $D/relgates_run1.log | tail -2 | cut -c1-300
echo END
