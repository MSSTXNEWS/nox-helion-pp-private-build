cd /workspace/nox/web/site
for pg in cinema music board dispatcher memory downloads studio; do echo "$pg: $(grep -o '<body[^>]*>' $pg.html | head -1) | wrap=$(grep -c 'class="wrap"' $pg.html) embed=$(grep -c nox-svc-embed $pg.html) main=$(grep -o '<main[^>]*>' $pg.html|head -1)"; done
tail -3 /workspace/nox/invoke_install.log | cut -c1-200
