"""D06 R8 native owner settings contract; source-only, not an owner-PC PASS."""
from pathlib import Path
import re, sqlite3, tempfile, subprocess
from contextlib import closing
root = Path(__file__).resolve().parent
native = (root/'src/MainWindow.xaml.cs').read_text(encoding='utf8')
web = (root/'src/index.html').read_text(encoding='utf8')
for token in (
    'case "settings.put": HandleSettingsPut(request); break;',
    'fields.Length != 3',
    'NOX_SETTINGS_INVALID_REQUEST',
    'NOX_SETTINGS_REJECTED',
    'db.BeginTransaction()',
    'tx.Commit();',
    'ReadPreferencesDictionary(); // independent read after SQLite COMMIT',
    'settings_wpf_owner_sqlite_readback',
    'case "stop":',
):
    assert token in native, token
for token in (
    "case 'settings.receipt':",
    "case 'settings.denied':",
    'id="personaStatus" class="mono" role="status" aria-live="polite"',
    "window.noxVisual?.setMode(v?.performance||'BALANCED')",
    '<body class="reduced">',  # Safe static frame until native SQLite motion preference arrives.
    'prefers-reduced-motion: reduce',
):
    assert token in web, token
assert 'MAX сохранён для реальных параметров генерации' not in web
with tempfile.TemporaryDirectory() as temp:
    file = Path(temp)/'isolated.sqlite3'
    with closing(sqlite3.connect(file)) as conn:
        conn.execute('CREATE TABLE preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        for mode in ('MAX','BALANCED','ECO'):
            conn.execute('INSERT INTO preferences(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('performance',mode))
            conn.commit()
            assert conn.execute("SELECT value FROM preferences WHERE key='performance'").fetchone()[0] == mode
    with closing(sqlite3.connect(file)) as conn:
        assert conn.execute("SELECT value FROM preferences WHERE key='performance'").fetchone()[0] == 'ECO'
scripts = re.findall(r'<script[^>]*>(.*?)</script>', web, re.S)
assert len(scripts) == 2
for script in scripts:
    # Explicit UTF-8 stdin is required: Windows GitHub runners default to cp1252.
    check = subprocess.run(['node','--check'], input=script.encode('utf-8'), capture_output=True)
    assert check.returncode == 0, check.stderr.decode('utf-8', errors='replace')
print('D06 R8 SETTINGS SOURCE_ONLY: validation/readback/ARIA/JS PASS; Windows owner-PC not tested')
