S=/workspace/nox/web/site; cd $S
wc -c nox-wow.js nox-wow.css nox-unify.css nox-identity.js
export PATH=/workspace/nox/tools/node/bin:$PATH; node -v; cd /tmp && rm -rf w3npm && mkdir w3npm && cd w3npm && timeout 100 npm pack highlight.js@11 2>&1 | tail -2; ls
cd $S
echo ==MSGDOM; grep -n -o "className *= *[\"'][a-z0-9 _-]*[\"']" nox-wow.js | sort -u -t: -k3 | head -60
echo ==FETCH; grep -n -o "fetch([^)]\{0,90\}" nox-wow.js | head -40
echo ==THREADS; grep -n "threadList\|thNew\|function renderThreads\|conv_id\|conversation_id" nox-wow.js | cut -c1-220 | head -40
echo ==FB; grep -n "feedback\|👍\|thumb" nox-wow.js | cut -c1-260 | head
echo ==MD; grep -n "marked\|DOMPurify\|renderMd\|function md" nox-wow.js | cut -c1-200 | head
echo ==THINK; grep -n "think\|typing\|dots" nox-wow.js | cut -c1-200 | head -20
