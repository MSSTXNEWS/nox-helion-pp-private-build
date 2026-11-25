echo S4RUN:s4_fin_fix
cd /workspace/nox/web/site
echo before: $(grep -c "nox-s4-lead" finance.html) s1: $(grep -c "nox-fin-s1" finance.html)
cp finance.html finance.html.bak_s4_fin
sed -i 's|<link rel="stylesheet" href="./nox-s4-lead.css">||; s|<script src="./nox-s4-lead.js" data-lead="finance" defer></script>||' finance.html
echo after: $(grep -c "nox-s4-lead" finance.html) s1: $(grep -c "nox-fin-s1" finance.html)
grep -c "S4 finance\|раскладка лидера (finance)" qa/rework/finance.fixed 2>/dev/null && rm -f qa/rework/finance.fixed
ls -la finance.html* | awk '{print $5,$6,$7,$8,$9}'
