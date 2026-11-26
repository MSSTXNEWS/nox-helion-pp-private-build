echo "C300: ui_st2"
F=/workspace/nox/web/v29src/FASTWOW/site; S=/workspace/nox/web/site
wc -c $F/studio.html $S/studio.html; grep -c "<select" $F/studio.html $F/nox-theme-studio-v4.js
grep -o '<script[^>]*src="[^"]*"\|<link[^>]*href="[^"]*css[^"]*"' $F/studio.html | sed 's/.*\(src\|href\)=//' | tr '\n' ' '
echo; grep -o 'data-nox-[a-z-]*="[^"]*"' $F/studio.html | sort -u | head -20 | tr '\n' ' '
echo; for f in $(grep -o '\(src\|href\)="[^"]*\.\(js\|mjs\|css\)' $F/studio.html | sed 's/.*="//;s/^\.\///;s/?.*//'); do [ -e $S/$f ] && echo "have $f" || { [ -e $F/$f ] && echo "MISSING-onsite(in FASTWOW) $f" || echo "NOWHERE $f"; }; done
echo "== disk"; df -h /workspace | tail -1; du -sh /workspace/nox/web/v29src /workspace/nox/web/v29src/* 2>/dev/null; find /workspace/nox/web/v29src -maxdepth 2 -name "*.zip" | xargs ls -la 2>/dev/null | awk '{print $5,$9}'; du -sh /workspace/nox/web/pkg_webroot_bak_* /workspace/nox/web/th_* 2>/dev/null | tail -3
