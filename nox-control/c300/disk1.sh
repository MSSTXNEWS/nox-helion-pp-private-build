echo "K1: disk1"
df -BG /workspace | awk 'NR==2{print "disk",$2,"used",$3,"free",$4}'
du -xsh /workspace/* 2>/dev/null | sort -rh | head -12
echo "-- nox"; du -xsh /workspace/nox/* 2>/dev/null | sort -rh | head -12
echo "-- state"; du -xsh /workspace/nox/state/* 2>/dev/null | sort -rh | head -10
echo "web_bak $(du -csh /workspace/nox/state/web_bak_* 2>/dev/null | tail -1)"
echo "-- caches"; du -xsh /root/.cache/* /workspace/nox/mods/*/ 2>/dev/null | sort -rh | head -8
echo END
