cd /workspace/nox/web/site
python3 - <<'P'
import re
s=open('editor.html',encoding='utf-8').read()
s=re.sub(r'<meta http-equiv="refresh"[^>]*><script>location\.replace\("creative\.html"\)</script>','',s)
s=s.replace('<title>NOX · РЕДАКТОР','<title>NOX · PDF И ДОКУМЕНТЫ')
open('pdf.html','w',encoding='utf-8').write(s); print('pdf ok', 'creative' in s)
P
sed -i 's#nox-editor-s1.js?v=[0-9]*#nox-editor-s1.js?v='$(date +%s)'#' pdf.html
cp qa/rework/editor.fixed qa/rework/pdf.fixed 2>/dev/null; echo "NB: editor.html перенаправлен другим исполнителем на creative.html, страница PDF+Код доступна как pdf.html (S1)." >> qa/rework/pdf.fixed
cd /tmp; /workspace/nox/venv/bin/python /workspace/nox/tools/s1_shot.py pdf.html pdf1 vp=pc,mob,4k 2>&1 | cut -c1-900
