echo "C300: tr_data3b"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
pgrep -f build_dpo3.py >/dev/null && echo "уже идёт" || { (cd $D && setsid -f nohup nice -n 8 $PY -I build_dpo3.py 110 >> $D/build3.log 2>&1 < /dev/null); sleep 5; }
pgrep -f build_dpo3.py | head -1; echo END
