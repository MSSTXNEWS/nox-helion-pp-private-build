echo "C300: ui_wd7 (скрины миров фоном)"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ui_worlds/shots.py -o /tmp/shots.py
rm -rf /tmp/shout; mkdir -p /tmp/shout
cat > /tmp/shrun.sh <<'B'
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
for w in helion chronos somnium forge synapse; do timeout 150 $PY /tmp/shots.py index 1440 900 ix_$w $w > /tmp/shout/ix_$w.txt 2>&1; done
for w in helion forge; do timeout 150 $PY /tmp/shots.py settings 1440 900 st_$w $w > /tmp/shout/st_$w.txt 2>&1; timeout 150 $PY /tmp/shots.py system 1440 900 sy_$w $w > /tmp/shout/sy_$w.txt 2>&1; done
for w in helion chronos; do timeout 150 $PY /tmp/shots.py index 390 844 m_$w $w > /tmp/shout/m_$w.txt 2>&1; done
for w in helion forge; do timeout 200 $PY /tmp/shots.py index 2560 1440 w_$w $w > /tmp/shout/w_$w.txt 2>&1; done
echo ALLDONE > /tmp/shout/DONE
B
setsid -f bash /tmp/shrun.sh </dev/null >/dev/null 2>&1; sleep 2; echo started
