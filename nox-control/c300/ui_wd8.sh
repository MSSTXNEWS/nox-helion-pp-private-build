echo "C300: ui_wd8 (результат скринов)"
ls /tmp/shout; for f in /tmp/shout/*.txt; do grep "^SH" $f | cut -c1-260; done
for f in /tmp/shout/*.txt; do grep "^B64" $f; done
