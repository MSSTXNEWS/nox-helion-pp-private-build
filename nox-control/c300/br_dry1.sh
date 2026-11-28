echo "K1: br_dry1"
# Проверка «ритуала рождения» без необратимого шага (dry-run, без --go).
N=/workspace/nox; cd $N/mods || exit 0
python3 -I birth_ritual.py 2>&1 | grep -oE '"(ok|delta_sha|reload_ok|test_pass|tests|passed|failed|born_at|ready|missing)"[^,}]*' | sed -E 's/[0-9a-f]{12,}/<sha>/g' | head -20
python3 -I conscience.py --selftest 2>&1 | tail -4 | grep -oE '[A-Za-z0-9_ ]*[0-9]+/[0-9]+'
echo "born_at_set=$(grep -c born_at $N/canon/*.json 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')"
echo END
