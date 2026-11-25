echo S4RUN:s4_rev1
cd /workspace/nox/web/site/qa/rework; for p in calendar dispatcher downloads events projects settings system training growth consciousness; do echo "== $p"; head -c 1100 $p.json; echo; done
