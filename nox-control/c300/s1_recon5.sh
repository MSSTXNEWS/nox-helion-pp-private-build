S=/workspace/nox/web/site
cd $S
grep -n "const URL\|GLM\b.*=\|'/glm\|\"/glm\|/api/chat\|NDJSON\|fetch(" nox-wow.js | cut -c1-260 | head -40
echo ==L110; sed -n 105,125p nox-wow.js | cut -c1-1800
echo ==SEND; sed -n 140,200p nox-wow.js | cut -c1-700
echo ==ALLREL; grep -rnoE "(fetch|EventSource)\(['\"\`][^/'\"\`h][^'\"\`]*" --include=*.js . 2>/dev/null | grep -v "/vendor/\|bak_" | head -30
grep -o "fetch([^)]\{0,80\}" vendor/nox-chat-ui/*.js | grep -v "http" | sort | uniq -c | head -20
