"""R8 native IPC/STOP/provider source regression. SOURCE_ONLY, never owner-PC acceptance."""
from pathlib import Path
import subprocess
import shutil
import re

root = Path(__file__).resolve().parent  # CI stages this test beside src/ inside r8/
cs = (root / "src" / "MainWindow.xaml.cs").read_text(encoding="utf-8")
html = (root / "src" / "index.html").read_text(encoding="utf-8")
required_cs = (
    'private string? activeRequestId;',
    'NavigationStarting += (_, _) => { active?.Cancel(); activeRequestId = null; };',
    'string.Equals(activeRequestId, Text("requestId"), StringComparison.Ordinal)',
    'case "chat": await Generate(Text("text"), Text("requestId"));',
    'private async Task Generate(string prompt, string requestId)',
    'requestId.Length < 8 || requestId.Length > 128',
    'if (string.Equals(activeRequestId, requestId, StringComparison.Ordinal)) Send(type, value);',
    'cancellation.Token.ThrowIfCancellationRequested();',
    'Emit("token", new { requestId, text = value });',
    'Emit("complete", new { requestId, ok = answer.Length > 0',
    'Emit("complete", new { requestId, ok = false, stopped = true });',
    'Emit("complete", new { requestId, ok = false, stopped = false });',
    'activeRequestId = null;',
    'TimeSpan.FromSeconds(4)',
    'TimeSpan.FromSeconds(3)',
    'PROVIDER_UNREACHABLE:',
    'OLLAMA_HTTP_ERROR:',
    'catch (OperationCanceledException) when (cancellation.IsCancellationRequested)',
    'catch (OperationCanceledException) {',
    'OLLAMA_TIMEOUT:',
)
required_html = (
    'activeChatId=nextChatId()',
    "post('chat',{text,requestId:activeChatId})",
    "post('stop',{requestId:activeChatId})",
    "v.requestId!==activeChatId",
    "case 'token':lastAnswer+=v.text",
    "case 'complete':busy=false;activeChatId=null",
    "Only the matching native complete may unlock a busy chat.",
    "if(e.key==='Escape'&&busy&&activeChatId){e.preventDefault();$('stop').click()}",
)
for fragment in required_cs:
    assert fragment in cs, 'B02_NATIVE_IPC_SOURCE_HOLD: ' + fragment
for fragment in required_html:
    assert fragment in html, 'B02_WEBVIEW2_SOURCE_HOLD: ' + fragment
# Ensure the previous unowned chat path cannot accidentally remain.
assert 'case "chat": await Generate(Text("text"));' not in cs
assert "case 'error':$('status').textContent='ERROR';entry($('messages'),String(v)" not in html
script_parts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", html, re.I)
assert len(script_parts) >= 2, "B02_WEBVIEW2_SCRIPT_HOLD"
if shutil.which('node') is None:
    raise SystemExit('B02_NODE_RUNTIME_MISSING_HOLD')
for source in script_parts:
    result = subprocess.run(['node','--check','-'],input=source.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')

# Windows SQLite open-file first-fail #42276488855: Microsoft.Data.Sqlite
# pooled backup handles must be closed before checksum reads of the checkpoint.
# This is a SOURCE_ONLY guard; Windows smoke validates the real file handles.
snapshot = cs.split('private string CheckpointSqlite(', 1)[1].split('private static bool HasPersonaColumn(', 1)[0]
assert snapshot.count('Pooling = false') == 2, 'B02_SQLITE_BACKUP_POOLING_HOLD'
assert re.search(r'DataSource\s*=\s*file,\s*Mode\s*=\s*SqliteOpenMode\.ReadWriteCreate,\s*Pooling\s*=\s*false', snapshot)
assert re.search(r'DataSource\s*=\s*file,\s*Mode\s*=\s*SqliteOpenMode\.ReadOnly,\s*Pooling\s*=\s*false', snapshot)
assert snapshot.index('PRAGMA quick_check') < snapshot.index('File.ReadAllBytes(file)'), 'B02_SQLITE_BACKUP_INTEGRITY_ORDER_HOLD'

print('B02 R8 IPC SOURCE_ONLY: owner-correlated stream/STOP, offline probe, JS parse PASS; real Windows Ollama NOT_TESTED')

# B04 source-only guard; executable/owner-Qwen are not claimed as tested.
generate = cs.split('private async Task Generate(', 1)[1].split('private void PersistChat(', 1)[0]
persist = cs.split('private void PersistChat(', 1)[1].split('private object ReadHistory(', 1)[0]
assert 'CancellationTokenSource.CreateLinkedTokenSource(cancellation.Token)' in generate
assert 'readWindow.CancelAfter(TimeSpan.FromMinutes(3))' in generate
assert 'await reader.ReadLineAsync(readWindow.Token)' in generate
assert 'catch (OperationCanceledException) when (cancellation.IsCancellationRequested)' in generate
assert 'catch (OperationCanceledException) {' in generate and 'OLLAMA_TIMEOUT:' in generate
assert generate.index('cancellation.Token.ThrowIfCancellationRequested();\n            if (answer.Length > 0) PersistChat') < generate.index('Emit("complete", new { requestId, ok = answer.Length > 0')
assert 'cmd.ExecuteNonQuery() != 1' in persist
assert 'last_insert_rowid()' in persist
assert 'using var verifyDb = OpenDatabase();' in persist
assert 'FROM chat_history WHERE id=$id' in persist
assert 'NOX_CHAT_SQLITE_READBACK_HOLD' in persist
print('B04 R8 SOURCE_ONLY: timeout vs owner STOP, committed-row readback PASS; owner Windows Qwen NOT_TESTED')
