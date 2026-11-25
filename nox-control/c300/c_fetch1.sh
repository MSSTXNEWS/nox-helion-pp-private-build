echo "C300: c_fetch1"
echo "== deploy log tail"; grep -v "^+" /workspace/nox/state/c_deploy.log | tail -40 | cut -c1-300
echo "== test out"; cat /workspace/nox/state/c_test1.out 2>&1 | cut -c1-900 | tail -40
echo "== state"; ls /workspace/nox/svc/pipeline; curl -s -m3 localhost:18217/health; echo; grep -c _pipe_after /workspace/nox/web/pkg/server/chat_core.py; grep -c metaset /workspace/nox/svc/living/living_svc.py
