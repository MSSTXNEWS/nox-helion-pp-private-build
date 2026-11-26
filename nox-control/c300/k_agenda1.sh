echo "C300: k_agenda1"
for p in agenda agenda/check night learned; do echo "== $p"; curl -s -m 15 http://127.0.0.1:8810/worms/$p | head -c 1500; echo; done
