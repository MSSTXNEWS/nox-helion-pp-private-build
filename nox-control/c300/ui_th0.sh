echo "C300: ui_th0"; S=/workspace/nox/web/site; cd $S; date; echo TZ $(date +%Z)
ls -la --time-style=full-iso nox-theme.js nox-wow-bg.js nox-graphite.css nox-graphite-map.css nox-motion.js nox-motion.css nox-th-fix.css nox-icons.js nox-logo.svg nox-wow.js nox-nav.js nox-ds.js nox-actions.js chat.html index.html 2>&1 | cut -c1-140
echo "== files mtime window"; find . -maxdepth 1 -type f -newermt "$(date -d '-6 hours' '+%F %T')" ! -newermt "$(date -d '-1 hours' '+%F %T')" -printf '%TF %TT %s %p\n' 2>/dev/null | sort | awk '{print $2" "$3" "$4}' | cut -c1-60 | awk '{c[substr($1,1,5)]++; if(c[substr($1,1,5)]<4)print}' | head -60
echo "== count per minute"; find . -maxdepth 1 -type f -printf '%TF %TH:%TM\n' | sort | uniq -c | sort -k3 | tail -25
echo "== baks"; ls -d /workspace/nox/web/*bak* /workspace/nox/web/th_* 2>/dev/null | tail -20
echo "== head nox-theme.js"; head -c 700 nox-theme.js
echo; grep -c data-nox-theme chat.html index.html settings.html
ls vendor/lucide 2>&1 | head -3; ls vendor/lucide/icons 2>/dev/null | wc -l
