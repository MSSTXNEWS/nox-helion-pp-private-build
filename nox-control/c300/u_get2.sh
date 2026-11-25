echo "C300: u_get2"
echo "== mqa2"; grep -v "^$" /tmp/u_mqa2.out | cut -c1-300 | head -30
echo "== mini"; cut -c1-400 /tmp/u_mini.out | head -10
echo "== audit"; cut -c1-380 /tmp/u_aud.out | head -80
