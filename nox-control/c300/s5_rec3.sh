S=/workspace/nox/web/site
sed -n 1,101p /workspace/nox/web/pkg/server/nox_cmd.py | cut -c1-220
echo "### training buttons"; grep -o -i "apply[a-zA-Z_-]*\|distill[a-zA-Z_-]*\|export[a-zA-Z_-]*\|download[a-zA-Z_-]*\|/api/[a-z_/-]*train[a-z_/-]*\|/train[a-z_/-]*" $S/training.html $S/nox-*train*.js 2>/dev/null | sort | uniq -c | head -30
ls $S | grep -i train
echo "### server routes"; grep -n "train\|distill\|dispatcher" /workspace/nox/web/pkg/server/web_server.py | head -30 | cut -c1-200
