echo "C300: ux_crit3"
D=/workspace/nox/state/mock_qa; mkdir -p $D; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/900dcbdeb5784ee18264984b913f4ce4d1433743/nox-control/c300/bundles/ux_crit
[ -s $D/after_system.jpg ] || for t in before after; do for p in system widgets memory map cinema knowledge projects pdf atlas board qa about integrations; do curl -fsSL --retry 3 $RAW/${t}_$p.jpg -o $D/${t}_$p.jpg || echo MISS; done; done
curl -fsSL $RAW/crit.py -o /tmp/ux_crit.py; ls $D | wc -l
rm -f /workspace/nox/agent/out/ux_c_prog.txt; setsid -f nohup python3 /tmp/ux_crit.py >/workspace/nox/agent/out/ux_c.log 2>&1 </dev/null
sleep 20; cat /workspace/nox/agent/out/ux_c_prog.txt 2>&1 | cut -c1-300; tail -3 /workspace/nox/agent/out/ux_c.log
