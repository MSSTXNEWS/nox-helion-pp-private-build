echo "C300: ux_crit2"
D=/workspace/nox/state/mock_qa; mkdir -p $D; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/ed687c7f984e723333f69625921a9a4f54ab23c2/nox-control/c300/bundles/ux_crit
for t in before after; do for p in system widgets memory map cinema knowledge projects pdf atlas board qa about integrations; do curl -fsSL --retry 3 $RAW/${t}_$p.jpg -o $D/${t}_$p.jpg || echo MISS $t $p; done; done
curl -fsSL $RAW/crit.py -o /tmp/ux_crit.py; ls $D | wc -l
rm -f /workspace/nox/agent/out/ux_c_prog.txt; setsid -f nohup python3 /tmp/ux_crit.py >/workspace/nox/agent/out/ux_c.log 2>&1 </dev/null
sleep 45; cat /workspace/nox/agent/out/ux_c_prog.txt 2>&1 | cut -c1-300; tail -3 /workspace/nox/agent/out/ux_c.log
