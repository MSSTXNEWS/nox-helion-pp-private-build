echo "C300: ux_get_c"
O=/workspace/nox/agent/out; cat $O/ux_c_prog.txt 2>&1 | cut -c1-260; pgrep -fa ux_crit.py | head -2
