cd /workspace/nox/web/site; ls -la editor.html* | tail -6; grep -c "nox-editor-s1" editor.html; grep -o "<title>[^<]*" editor.html; grep -l "nox-editor-s1" *.html
