export RUNNER_TRACKING_ID=""
echo "C300: tr_img1"
N=/workspace/nox
grep -rln "korea_img_disabled" $N --include=*.py --include=*.sh --include=*.js --include=*.json 2>/dev/null | grep -v -E "bak|/c300/|node_modules" | head -8
for f in $(grep -rln "korea_img_disabled" $N --include=*.py 2>/dev/null | grep -v -E "bak|c300" | head -3); do echo "#### $f"; grep -n "korea_img_disabled" $f | cut -c1-200 | head -4; done
ss -ltnp | grep -E ":(8188|8189|8190|8700|8701|8800|18300)\b" | awk '{print $4}' | tr '\n' ' '; echo
ls $N/state | grep -i -E "img|korea|flux|draw" | head -12
echo END
