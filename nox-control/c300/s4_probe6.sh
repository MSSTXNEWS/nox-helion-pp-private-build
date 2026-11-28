N=/workspace/nox
echo "S4P6 $(date +%F_%H:%M)"
echo "## matrix"; cat $N/state/core/autonomy_matrix.json 2>/dev/null | head -c 3500
echo; echo "## users/memory layout"; ls $N/state/core | head -40; ls $N/state | grep -i -E "user|dima|memory|s03" | head
echo "## s03 api"; grep -n "def \|user" $N/web/pkg/server/s03*.py 2>/dev/null | head -30; ls $N/mods | head -60
echo "## who consumes matrix"; grep -rIl --include=*.py "autonomy_matrix" $N/web $N/mods $N/agent $N/ops 2>/dev/null | head
