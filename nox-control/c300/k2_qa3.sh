echo "C300: k2_qa3"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
sed -i 's#127.0.0.1:8090/web/#127.0.0.1:8091/web/#; s#127.0.0.1:8080/web/#127.0.0.1:8091/web/#' /tmp/k2_qa.py
echo "idx $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/web/index.html)"
timeout 200 $PY /tmp/k2_qa.py index system growth news memory chat pdf assistant knowledge 2>&1 | tail -20
ls -la /tmp/k2_shot.jpg
exit 0
