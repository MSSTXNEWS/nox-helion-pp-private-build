cd /tmp; for p in "atlas.html at3" "editor.html ed3"; do set -- $p; /workspace/nox/venv/bin/python /workspace/nox/tools/s1_shot.py $1 $2 vp=mob,4k 2>&1 | cut -c1-900; sleep 5; done
