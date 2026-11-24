# A: где объявлен маршрут /memory/api (только чтение)
grep -rln "/memory/api" /workspace/nox --include=*.py --include=*.js --include=*.sh 2>/dev/null | grep -v venv | head -8
for f in $(grep -rln "/memory/api" /workspace/nox --include=*.py 2>/dev/null | grep -v venv | head -3); do echo "== $f"; grep -n "memory/api" "$f" | head -3 | cut -c1-200; done
