echo "C300: ui_c1"
D=/workspace/nox/state/mock_qa; mkdir -p $D; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ui_crit
LIST="b0_index_1440.jpg b0_creative_1440.jpg b0_settings_1440.jpg"
for f in $LIST; do curl -fsSL --retry 3 $RAW/$f -o $D/$f || echo MISS $f; done
curl -fsSL $RAW/crit.py -o /tmp/ui_crit.py
rm -f /workspace/nox/agent/out/ui_c1_prog.txt
setsid -f nohup python3 /tmp/ui_crit.py c1 $LIST >/workspace/nox/agent/out/ui_c1.log 2>&1 </dev/null
sleep 100; cat /workspace/nox/agent/out/ui_c1_prog.txt 2>&1 | cut -c1-1200; tail -3 /workspace/nox/agent/out/ui_c1.log
