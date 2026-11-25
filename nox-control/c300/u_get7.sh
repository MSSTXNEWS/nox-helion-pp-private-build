echo "C300: u_get7"
for e in train/status system/live; do echo "== $e"; curl -s -m8 -w "\nHTTP %{http_code}\n" http://127.0.0.1:8091/svc/p3st/$e | cut -c1-700; done
