echo "C300: k2_qa1"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
sed -i 's#127.0.0.1:8080/web/#127.0.0.1:8090/web/#; s#errs.append(.goto .+str(e)\[:80\])#errs.append("goto "+str(e)[:80])#' /tmp/k2_qa.py
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8090/web/index.html
timeout 200 $PY /tmp/k2_qa.py index system growth news memory chat pdf assistant knowledge 2>&1 | tail -20
exit 0
