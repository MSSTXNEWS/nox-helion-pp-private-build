S=/workspace/nox/web/site
cd $S
echo ==MODES; grep -o '<div class="seg modes".*' chat.html | cut -c1-1500; grep -n 'splitName' chat.html | cut -c1-900
echo ==CSS; cat nox-chat-x.css
echo ==JS; cat nox-chat-x.js
