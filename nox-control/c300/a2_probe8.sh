echo "C300: a2_probe8"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/61784f49436134d0dfd4580a1cd013585f843a7d/nox-control/c300; A=/workspace/nox/agents
for f in a2_pool_probe.py a2_pool_measure.py; do curl -fsSL "$R/$f" -o $A/$f; done
setsid -f sh -c "python3 $A/a2_pool_measure.py 24 before > $A/measure_before.log 2>&1" </dev/null >/dev/null 2>&1
timeout 150 python3 $A/a2_pool_probe.py 2>&1 | cut -c1-420
md5sum /workspace/nox/advisors/gateway.py; wc -l /workspace/nox/advisors/gateway.py
