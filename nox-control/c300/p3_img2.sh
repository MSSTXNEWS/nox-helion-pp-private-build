N=/workspace/nox
echo "== test results"; cat $N/state/p3/img_test.txt; cat /tmp/p3_imgtest.err | tail -3
echo "== gateway images_generate"; sed -n 236,247p $N/advisors/gateway.py | cut -c1-260
echo "== ART module"; f=$(grep -n "^import\|^from" $N/advisors/gateway.py | grep -i art | head -2); echo "$f"; ls $N/advisors | head -20
a=$(ls $N/advisors/art*.py 2>/dev/null | head -1); echo "art=$a"; grep -n -E "def generate|prompt|seed|translate|cache|\.index|latest|sorted|listdir|glob|random|redact|personal" $a | cut -c1-200 | head -50
