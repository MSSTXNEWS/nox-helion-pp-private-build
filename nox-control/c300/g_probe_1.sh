S=/workspace/nox/web/site
cd $S && ls | head -150 | tr '\n' ' '; echo
echo NAV; head -c 1500 nav.json; echo
ls qa | head -30; echo SUM; head -c 4000 qa/summary.md
echo HTMLCOUNT $(ls *.html | wc -l)
du -sh vendor; ls vendor | wc -l
ls /workspace/nox/web/site/qa/shots 2>/dev/null | head -30; find $S -name '*.png' -newer $S/nav.json -maxdepth 3 | head
