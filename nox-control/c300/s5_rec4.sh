S=/workspace/nox/web/site
grep -n -i "apply\|distill\|export\|download\|NOXcmd\|fetch(" $S/nox-s4-training.js | cut -c1-260 | head -40
echo "### endpoints"; grep -rn "training/status\|/training" /workspace/nox/web/pkg/server/*.py 2>/dev/null | cut -c1-200 | head -12
for u in /api/nox/training/status /api/training/status /training/status /api/dispatcher/status /api/distill/status; do echo $u $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091$u); done
ls /workspace/nox/state | grep -i "train\|distill\|dispatch" | head; ls /workspace/nox/web/site/state 2>/dev/null | head -3
