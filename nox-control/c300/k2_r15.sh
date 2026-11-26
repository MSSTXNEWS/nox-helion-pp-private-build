echo "C300: k2_r15"
N=/workspace/nox
grep -rn "с Димой" $N/web/pkg/server/*.py $N/brain/BRAIN/*.py 2>/dev/null | cut -c1-260 | head -6
