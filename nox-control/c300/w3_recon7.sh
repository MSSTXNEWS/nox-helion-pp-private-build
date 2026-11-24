S=/workspace/nox/web/site; cd $S
head -c 1500 events.html; echo
grep -l "events" nox-*.js | head; grep -o "['\"][^'\"]*events[^'\"]*['\"]" nox-api.js nox-registry.js nox-p-system.js nox-notify.js nox-wow-data.js 2>/dev/null | sort -u | head -20
for u in /api/events /glm/v1/nox/events /api/nox/events /api/nox/outbox; do echo "-- $u"; curl -s -m 8 127.0.0.1:8091$u | head -c 400; echo; done
