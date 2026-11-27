echo "K1: l1_slot1"
cd /workspace/nox
for f in agent/nox_agents/lib.py agent/nox_agents/inner_loop.py agent/nox_agents/chat_speed_watch.py agent/nox_agents/selfheal.py ops/sun_adapter/sun_adapter.py svc/s2_podcast.py ops/p3_status_svc.py; do echo "## $f"; grep -n "8104\|id_slot\|8105" $f | cut -c1-210 | head -8; done
