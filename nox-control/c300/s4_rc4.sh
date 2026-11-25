S=/workspace/nox/web/site
grep -o 'nox-p-[a-z]*\.js' $S/projects.html $S/memory.html $S/events.html $S/calendar.html $S/system.html $S/downloads.html $S/settings.html | sort -u
echo == projects html body; sed -n '/<body/,/<\/main>/p' $S/projects.html | cut -c1-1800
echo == js; J=$(grep -o 'nox-p-[a-z]*\.js' $S/projects.html | head -1); wc -c $S/$J; grep -n -E "localStorage|Dexie|\.add\(|columns|status|due|id:" $S/$J | head -40 | cut -c1-260
echo == dl; sed -n '/<body/,/<\/main>/p' $S/downloads.html | cut -c1-900; curl -s -m4 -o /dev/null -w 'fb %{http_code}\n' 127.0.0.1:8091/svc/filebrowser/
