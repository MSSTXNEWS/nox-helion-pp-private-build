cd /workspace/nox/web/site
echo 'label.ed-btn.pri,.ed-bar .ed-btn.pri{color:#fff!important;opacity:1!important;background:linear-gradient(160deg,#ff8a50,#e5541f)!important;text-shadow:0 1px 2px rgba(0,0,0,.45);font-weight:600}' >> nox-editor-s1.css
for f in pdf.html editor.html assistant.html; do sed -i 's#nox-editor-s1.css?v=[0-9]*#nox-editor-s1.css?v='$(date +%s)'#' $f; done; echo done
