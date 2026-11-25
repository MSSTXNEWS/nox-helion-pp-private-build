cd /workspace/nox/web/site; grep -o 'id="[a-zA-Z]*"' chat.html | tr '\n' ' ' | head -c 1800; echo; grep -o 'class="[a-z ]*feed[a-z ]*"\|class="[a-z ]*stream[a-z ]*"' chat.html | head -3
