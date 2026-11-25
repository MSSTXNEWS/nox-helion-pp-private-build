echo "C300: a2_gwdiff"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build; G=/workspace/nox/advisors
for c in 5aa50b2e8e5d992bacd3c9040a88bac0cc989acf 7628731e6818a65feb3da9b38001818150ca5809 07820666fa44ea31de3a02fa5190d8fa912df04e ; do curl -fsSL "$R/$c/nox-control/c300/v_gw_gateway.py" -o /tmp/gw_$c.py; echo $c $(md5sum < /tmp/gw_$c.py | cut -c1-8); done
ls -la --time-style=full-iso $G/gateway.py* | cut -c30-140
echo "== diff bak vs repo-prev"; for c in 5aa50b2e8e5d992bacd3c9040a88bac0cc989acf 7628731e6818a65feb3da9b38001818150ca5809 07820666fa44ea31de3a02fa5190d8fa912df04e ; do diff /tmp/gw_$c.py $G/gateway.py.bak_a2_gw3 >/tmp/d_$c.txt && { echo "SAME as $c"; }; done
c=7628731e6818a65feb3da9b38001818150ca5809; diff /tmp/gw_$c.py $G/gateway.py.bak_a2_gw3 | cut -c1-300 | head -40
