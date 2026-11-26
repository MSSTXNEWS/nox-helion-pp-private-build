echo "C300: k2_m3"
grep -n -B2 -A2 "meili_key" /workspace/nox/web/pkg/server/nox_extra.py /workspace/nox/web/pkg/server/nox_cmd.py | grep -vE "^--$" | sed -E 's/[A-Za-z0-9]{30,}/***/g' | cut -c1-170
