echo "C300: ui_rm1"
S=/workspace/nox/web/site; V=/workspace/nox/web/pkg/vendor
echo "== site/vendor"; ls $S/vendor 2>/dev/null | head -80; echo "== pkg/vendor"; ls $V 2>/dev/null | head -80
echo "== per page: size, external libs, inline script bytes"
for p in index creative settings system memory map knowledge widgets projects music news cinema mail calendar tools studio photo voice training dispatcher downloads board atlas pdf integrations assistant writer; do
 f=$S/$p.html; [ -f $f ] || { echo "$p MISSING"; continue; }
 libs=$(grep -o 'src="[^"]*"' $f | sed 's/src="//;s/"//;s/?.*//' | grep -v 'nox-\(nav\|theme\|motion\|wow\|4k\|u-ux\|s6\)' | xargs -n1 basename 2>/dev/null | sort -u | tr '\n' ' ')
 inl=$(python3 -c "import re,sys;s=open('$f',errors='ignore').read();print(sum(len(m) for m in re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>',s,re.S)))")
 echo "$p $(stat -c%s $f)B inline_js=$inl libs: $libs"
done
