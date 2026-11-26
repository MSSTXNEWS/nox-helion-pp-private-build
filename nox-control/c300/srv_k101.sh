echo "C300: srv_k101"
cd /workspace/nox
sed -n 120,185p imgsvc/image_service.py | cut -c1-200
echo ---; grep -n "OWNER_ACTIVE\|owner_active\|LIVE_TURN\|trainer_busy\|training" imgsvc/image_service.py | head
ls state/orch | head -20; cat state/orch/owner_active.state 2>/dev/null | head -3
