echo "C300: srv_k143"
cd /workspace/nox/web/pkg/server
grep -n "думает долго\|advisors_un\|enable_thinking\|max_tokens\|LOCAL_WAIT\|local_first\|stream" web_server.py | cut -c1-190 | head -40
ls ..; ls | head -30
