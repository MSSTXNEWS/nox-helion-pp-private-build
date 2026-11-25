cd /workspace/nox/web/site
python3 - <<'P'
import json
d=json.load(open('nav.json'))
for g in d.get('groups',[]):
    for i in g['items']:
        if any(k in (i.get('file','')+i.get('title','')+i.get('name','')).lower() for k in ('pdf','док','book','editor','код','constructor','assistant','помощ','atlas','voice','голос','knowledge','книг','редакт')): print(g.get('title') or g.get('name'),i)
P
for p in editor book-reader constructor; do echo "== $p $(wc -c <$p.html)"; sed -n '/<main/,/<\/main>/p' $p.html | cut -c1-500 | head -14; grep -o '<script[^>]*src="[^"]*"' $p.html | head -8; done
ls vendor/nox-x/monaco | head; ls vendor/pdfjs | head -5; ls vendor/nox-extra | head -30 | tr '\n' ' '
echo; ls vendor/nox-planets | head -8
