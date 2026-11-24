S=/workspace/nox/svc
curl -s -m10 localhost:8096/svc/jellyfin/web/index.html | sed 's/<[^>]*>//g' | tr -s ' \n' | head -c 300; echo
ls $S/data/jellyfin/log 2>/dev/null | head -3; tail -5 $S/data/jellyfin/log/*.log 2>/dev/null | cut -c1-220
ls $S/jellyfin | head -30; ls $S/jellyfin/jellyfin-web 2>&1 | head -3
