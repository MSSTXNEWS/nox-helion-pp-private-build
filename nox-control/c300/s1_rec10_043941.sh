cd /workspace/nox/web/site/vendor
ls nox-liquid-glass nox-x | head -40; cat nox-liquid-glass/README* 2>/dev/null | head -30; ls nox-x/* | head -30
du -sh nox-liquid-glass nox-x/* 2>/dev/null | head
grep -n "9.4\|F1\|2.4\|17.1" /workspace/nox/web/site/../../../nox/web/site/qa/IDEAS.md 2>/dev/null | head -3
