echo "C300: srv_k102"
cd /workspace/nox
sed -n 150,160p imgsvc/image_service.py
ls -la state/orch/OWNER_ACTIVE; cat state/orch/OWNER_ACTIVE | head -3; tail -n 3 state/orch/owner_active.log | cut -c1-200
pgrep -fa image_service | cut -c1-120; grep -n "image_service\|imgsvc" /etc/supervisor/conf.d/*.conf | head -3
grep -n "OWNER_ACTIVE" stewards/owner_active.py | head -5
