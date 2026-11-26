echo "C300: w_w0"
S=/workspace/nox/web/site
ls -la $S | grep -i -E 'writer|studio-roles|k8-draw' | awk '{print $5,$9}'
wc -c $S/writer.html; grep -o '<script[^>]*src="[^"]*"' $S/writer.html | sed 's/.*src=//' | tr '\n' ' '; echo
grep -o 'id="[^"]*"' $S/writer.html | head -60 | tr '\n' ' '; echo
sed 's/<[^>]*>/ /g' $S/writer.html | tr -s ' \n' ' ' | cut -c1-1200
grep -o '/api/[a-z_/\-]*' $S/writer.html $S/nox-writer*.js 2>/dev/null | sort -u | head -30
