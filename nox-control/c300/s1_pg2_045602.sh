cd /workspace/nox/web/site
ls *.html | grep -iv "bak" | tr '\n' ' '; echo
echo ==VOICEFULL; sed -n '/<main/,/<\/main>/p' voice.html | cut -c1-1800
echo ==VX; wc -c nox-voice-x.js nox-p-media.js; head -c 2500 nox-voice-x.js
echo ==ATLAS; sed -n '/<body/,/<\/body>/p' atlas.html | cut -c1-400 | head -50
echo ==ASSIST; sed -n '/<body/,/<\/body>/p' assistant.html | cut -c1-500 | head -40
grep -l "pdf" *.html | grep -v bak | head
