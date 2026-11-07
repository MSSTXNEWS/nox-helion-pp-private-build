"""D06 R8 native owner settings contract; source-only, not an owner-PC PASS."""
from pathlib import Path
import re, sqlite3, tempfile, subprocess
from contextlib import closing
root = Path(__file__).resolve().parent
native = (root/'src/MainWindow.xaml.cs').read_text(encoding='utf8')
web = (root/'src/index.html').read_text(encoding='utf8')
for token in (
    'case "settings.put": HandleSettingsPut(request); break;',
    'fields.Length != 4',
    'fields.Count(x => x.Name == "requestId") != 1',
    '!validId',
    'Send("settings.receipt", new { requestId, key, value, saved = true });',
    'NOX_SETTINGS_OWNER_RECEIPT_HOLD',
    'NOX_SETTINGS_COMMIT_UNKNOWN_HOLD',
    'case "settings.get": HandleSettingsGet(request); break;',
    'private void HandleSettingsGet(JsonElement request)',
    'Send("settings.readback", new { requestId, values });',
    'NOX_SETTINGS_READBACK_SQLITE_HOLD',
    'SavePreference(key, value, ref commitAttempted);',
    'commitAttempted = true;',
    'commitAttempted ? "NOX_SETTINGS_COMMIT_UNKNOWN_HOLD" : "NOX_SETTINGS_SQLITE_HOLD"',
    'NOX_SETTINGS_MOTION_RECEIPT_HOLD',
    "requestId:'smoke_foreign_0001'",
    'NOX_SETTINGS_INVALID_REQUEST',
    'NOX_SETTINGS_REJECTED',
    'db.BeginTransaction()',
    'tx.Commit();',
    'ReadPreferencesDictionary(); // independent read after SQLite COMMIT',
    'settings_wpf_owner_sqlite_readback',
    'settings_wpf_owner_restart_readback',
    'settings_wpf_motion_sqlite_readback',
    'settings_foreign_key_denial',
    'NOX_SETTINGS_RESTART_MOTION_SQLITE_HOLD',
    'NOX_SETTINGS_RESTART_MOTION_WEBVIEW2_HOLD',
    'NOX_SETTINGS_FOREIGN_KEY_WRITTEN_HOLD',
    'UiSmokeSettingsRestartRequested',
    'selftest_r8_',
    'case "stop":',
    'AutomationProperties.SetAutomationId(Browser, "NOX_HELION_WEBVIEW2")',
    'AutomationElement.FromHandle(uiaHandle)',
    'settings_windows_uia_host',
    'settings_webview2_accessible_controls',
    'NOX_SETTINGS_WINDOWS_UIA_HOST_HOLD',
):
    assert token in native, token
for token in (
    "case 'settings.receipt':",
    "case 'settings.denied':",
    'pendingSettings={requestId,key,value}',
    "post('settings.put',{key,value,requestId})",
    "v?.requestId!==pendingSettings.requestId",
    "applyCommittedSettings(committedSettings)",
    "NOX_SETTINGS_OWNER_IN_FLIGHT",
    "settingsReconcile=reconcile;setSettingsBusy(true)",
    "post('settings.get',{requestId:reconcile.requestId})",
    "case 'settings.readback':",
    "v?.requestId!==r.requestId",
    "clearTimeout(r.timer)",
    "NOX_SETTINGS_READBACK_TIMEOUT_HOLD",
    "'NOX_SETTINGS_COMMIT_UNKNOWN_HOLD'",
    'id="personaStatus" class="mono" role="status" aria-live="polite"',
    "window.noxVisual?.setMode(v?.performance||'BALANCED')",
    '<body class="reduced">',  # Safe static frame until native SQLite motion preference arrives.
    'prefers-reduced-motion: reduce',
    '<label for="persona">PersonaID</label>',
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
# D06_RECONCILE_BROADCAST_RUNTIME: execute the exact extracted original JS
# settings notification handler in Node, not a manually reimplemented mock.
# A generic settings broadcast may be stale while a correlated owner
# COMMIT_UNKNOWN readback is in progress; it must not replace the UI state.
settings_case = re.search(r"case 'settings':(.*?)break;", web, re.S)
assert settings_case, 'D06 settings handler missing'
runtime = r"""
'use strict';
const handler = new Function('pendingSettings', 'settingsReconcile',
  'v', 'applyCommittedSettings', String.fromCharCode(36), 'settingsDenial', HANDLER_CODE);
function verify(pending, reconcile, expectedApply) {
  let applied = 0;
  const status = {textContent: 'NOX_SETTINGS_COMMIT_UNKNOWN_HOLD'};
  handler(pending, reconcile, {performance:'BALANCED'}, () => applied++,
    () => status, 'NOX_SETTINGS_COMMIT_UNKNOWN_HOLD');
  if (applied !== expectedApply)
    throw new Error('D06_STALE_SETTINGS_BROADCAST_HOLD applied='+applied+
      ' expected='+expectedApply);
  if (status.textContent !== 'NOX_SETTINGS_COMMIT_UNKNOWN_HOLD')
    throw new Error('D06_OWNER_RECEIPT_STATUS_HOLD');
}
verify(null, {requestId:'r-confirm',key:'performance',value:'ECO'}, 0);
verify({requestId:'r-pending',key:'performance',value:'ECO'}, null, 0);
verify(null, null, 1);
""".replace('HANDLER_CODE', __import__('json').dumps(settings_case.group(1)))
runtime_check = subprocess.run(['node','-e',runtime], capture_output=True,
                                encoding='utf-8')
assert runtime_check.returncode == 0, runtime_check.stderr
print('D06 R8 SETTINGS SOURCE_ONLY: validation/readback/ARIA/JS PASS; Windows owner-PC not tested')
