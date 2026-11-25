echo "C300: u_get1"
echo "== svc advisors body"; curl -s -m 5 localhost:8091/svc/advisors/health | head -c 200; echo; curl -s -m 5 -X POST localhost:8091/svc/advisors/v1/images/generations -d '{}' | head -c 200; echo
echo "== mqa"; grep -v "^$" /tmp/u_mqa.out | cut -c1-330 | head -60
echo "== qa1"; cut -c1-330 /tmp/u_qa1.out | head -30
