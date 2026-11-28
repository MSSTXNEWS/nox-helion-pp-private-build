N=/workspace/nox
echo "S4P7 $(date +%F_%H:%M)"
F=$(find $N -name autonomy_matrix.json -not -path "*/venv*" 2>/dev/null | head -2); echo "matrix files: $F"
for f in $F; do head -c 3000 $f; echo; done
echo "## s03 service"; S=$(grep -rIl --include=*.py "18220" $N/mods $N/brain $N/web $N/ops 2>/dev/null | head -5); echo "$S"
for f in $S; do echo "## $f"; grep -n -i "user\|incognito\|def \|dima\|owner" $f | head -40 | cut -c1-220; done
