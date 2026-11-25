cd /workspace/nox/web/site/vendor && echo "VENDOR:" && ls -1 | tr '\n' ' '; echo
for d in nox-x nox-extra fx nox-lib; do [ -d $d ] && echo "$d: $(ls -1 $d | tr '\n' ' ')"; done
echo "NODE_MODULES:"; ls -1 /workspace/nox/web/build/node_modules 2>/dev/null | grep -v '^\.' | head -80 | tr '\n' ' '; echo
echo "SVC:"; ls -1 /workspace/nox/svc 2>/dev/null | tr '\n' ' '; echo
df -BG /workspace | tail -1
