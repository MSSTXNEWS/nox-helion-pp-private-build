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
    # D01's native post can fail: owner ID is committed only on dispatch success.
    "const requestId=nextChatId();if(post('chat',{text,requestId})===false)",
    'busy=true;activeChatId=requestId;',
    # Native D01 owner dispatch now sends fresh requestId, before it is assigned to activeChatId.
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
# A failed native bridge must not claim the active chat owner or lose a draft.
chat_handler = html.split("$('send').onclick=()=>", 1)[1].split("\n$('stop').onclick=", 1)[0]
assert chat_handler.index("if(post('chat',{text,requestId})===false)") < chat_handler.index("busy=true;activeChatId=requestId;"), "B02_PREMATURE_NATIVE_OWNER_HOLD"
assert chat_handler.count("post('chat',{text,requestId})") == 1, "B02_DUPLICATE_OWNER_DISPATCH_HOLD"
assert "post('chat',{text,requestId:activeChatId})" not in chat_handler, "B02_PREMATURE_ACTIVE_ID_DISPATCH_HOLD"
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
snapshot = cs.split('private string CheckpointSqlite(', 1)[1].split('private void VerifyIsolatedSqliteBackup(', 1)[0]
assert snapshot.count('Pooling = false') == 2, 'B02_SQLITE_BACKUP_POOLING_HOLD'
# B03 introduced a distinct third pooled-handle safeguard in its own smoke
# method. Do not count it as part of CheckpointSqlite or weaken its guard.
smoke_backup = cs.split('private void VerifyIsolatedSqliteBackup(', 1)[1].split('private static bool HasPersonaColumn(', 1)[0]
assert smoke_backup.count('Pooling = false') == 1, 'B03_SMOKE_BACKUP_POOLING_HOLD'
assert 'PRAGMA quick_check' in smoke_backup and 'NOX_B03_SMOKE_INTEGRITY_HOLD' in smoke_backup, 'B03_SMOKE_BACKUP_INTEGRITY_HOLD'
assert re.search(r'DataSource\s*=\s*file,\s*Mode\s*=\s*SqliteOpenMode\.ReadWriteCreate,\s*Pooling\s*=\s*false', snapshot)
assert re.search(r'DataSource\s*=\s*file,\s*Mode\s*=\s*SqliteOpenMode\.ReadOnly,\s*Pooling\s*=\s*false', snapshot)
assert snapshot.index('PRAGMA quick_check') < snapshot.index('string sha = Sha256File(file)'), 'B02_SQLITE_BACKUP_INTEGRITY_ORDER_HOLD'

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


# D05 SOURCE_ONLY regression: native write receipts must follow independent
# SQLite readback. WebView2 drafts must survive denial / offline bridge; only
# the matching owner request receipt may clear the matching draft.
for action, table in (("Task", "tasks"), ("Note", "memory_notes")):
    segment = cs.split(f"private void Handle{action}Add(", 1)[1].split("\n    private ", 1)[0]
    assert "ValidWriteRequestId(requestId)" in segment, "D05_OWNER_REQUEST_HOLD"
    assert "using var verifyDb = OpenDatabase();" in segment, "D05_READBACK_HOLD"
    assert f"FROM {table} WHERE id=$id" in segment, "D05_SQLITE_ROW_HOLD"
    assert segment.index("using var verifyDb") < segment.index(f'Send("{action.lower()}s.add.receipt"'), "D05_PREMATURE_ACK_HOLD"
    assert f'Send("{action.lower()}s.add.denied"' in segment, "D05_DENIAL_HOLD"
for part in (
    "pendingTask={requestId,text}",
    "pendingNote={requestId,title,content}",
    "if(post('tasks.add',{text,requestId})===false)",
    "if(post('notes.add',{title,content,requestId})===false)",
    "v?.requestId===pendingTask.requestId&&v.saved===true",
    "v?.requestId===pendingNote.requestId&&v.saved===true",
    "case 'tasks.add.denied':",
    "case 'notes.add.denied':",
):
    assert part in html, "D05_DRAFT_NOLOSS_HOLD " + part
assert "post('tasks.add',{text});$('taskInput').value=''" not in html
assert "post('notes.add',{title,content});$('noteTitle').value=''" not in html
print("D05 R8 SOURCE_ONLY: native task/note owner receipts after SQLite readback and draft NO-LOSS PASS")

# B04 native chat preflight denial must terminate the WebView2 owner.
# A native post succeeds before Generate determines capacity or validity.
# The UI intentionally unlocks ONLY on request-correlated complete, not error.
preflight = generate.split('using var cancellation = new CancellationTokenSource();', 1)[0]
assert 'void RejectChat(string reason)' in preflight, 'B04_CHAT_REJECT_HELPER_HOLD'
reject = preflight.split('void RejectChat(string reason)', 1)[1].split('if (string.IsNullOrWhiteSpace(prompt))', 1)[0]
assert 'Send("error", new { requestId, message = reason });' in reject, 'B04_CHAT_REJECT_REASON_HOLD'
assert 'Send("complete", new { requestId, ok = false, stopped = false });' in reject, 'B04_CHAT_REJECT_COMPLETE_HOLD'
for marker in ('CHAT_EMPTY_PROMPT_DENIED', 'CHAT_REQUEST_ID_DENIED',
               'CHAT_PROMPT_TOO_LONG_DENIED', 'CHAT_ALREADY_RUNNING_HOLD'):
    assert preflight.count('RejectChat("' + marker + '");') == 1, 'B04_CHAT_REJECT_PATH_HOLD ' + marker
assert "case 'complete':busy=false;activeChatId=null" in html, 'B04_WEBVIEW_CHAT_UNLOCK_HOLD'
print('B04 R8 SOURCE_ONLY: native preflight rejection now releases the matching WebView2 owner')

# B04 live HTTP STOP acceptance regression: a task/HTTP POST beginning is not
# evidence of a real streaming response. The self-test must wait for an actual
# nonempty Ollama NDJSON token before pressing WebView2 STOP.
selftest = cs.split('private async Task RunNativeSelfTestAsync()', 1)[1].split('private bool HasSavedPrompt(', 1)[0]
token_wait = cs.split('private async Task<bool> WaitForGenerationTokenAsync(', 1)[1].split('private async Task WaitForGenerationFinishAsync(', 1)[0]
generation = cs.split('private async Task Generate(', 1)[1].split('private void PersistChat(', 1)[0]
assert 'int streamTokenTarget = Volatile.Read(ref generationStreamingTokenCount) + 1;' in selftest
assert selftest.index('WaitForGenerationTokenAsync(streamTokenTarget, stopTarget, TimeSpan.FromMinutes(2))') < selftest.index('document.getElementById(\'stop\').click()')
assert 'NOX_ACTIVE_HTTP_STREAM_NOT_OBSERVED_HOLD' in selftest
assert 'Volatile.Read(ref generationFinishedCount) >= generationTarget' in token_wait
assert 'Volatile.Read(ref generationStreamingTokenCount) >= tokenTarget' in token_wait
assert 'if (value.Length > 0) Interlocked.Increment(ref generationStreamingTokenCount);' in generation
assert generation.index('await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation.Token)') < generation.index('Interlocked.Increment(ref generationStreamingTokenCount)')
print('B04 R8 SOURCE_ONLY: physical STOP oracle waits for live Ollama NDJSON token, not only native dispatch PASS')

# An HTTP NDJSON token is insufficient: the same live WebView2 document must
# render it before STOP, then visibly unlock after native HTTP cancellation.
visible = cs.split('private async Task<bool> WaitForVisibleChatTokenAsync(', 1)[1].split('private async Task<bool> WaitForStopUiReleaseAsync(', 1)[0]
released = cs.split('private async Task<bool> WaitForStopUiReleaseAsync(', 1)[1].split('private async Task WaitForGenerationFinishAsync(', 1)[0]
assert "document.getElementById('messages')?.firstElementChild" in visible
assert "label?.textContent === 'NOX QWEN'" in visible
assert "body.textContent === lastAnswer" in visible
assert "busy === true && activeChatId !== null" in visible
assert "document.getElementById('generation')?.classList.contains('on')" in visible
assert 'Volatile.Read(ref generationFinishedCount) >= generationTarget' in visible
assert 'NOX_WEBVIEW2_STREAM_TOKEN_NOT_VISIBLE_HOLD' in selftest
assert selftest.index('WaitForGenerationTokenAsync(streamTokenTarget, stopTarget, TimeSpan.FromMinutes(2))') < selftest.index('WaitForVisibleChatTokenAsync(stopTarget, TimeSpan.FromSeconds(4))') < selftest.index("document.getElementById('stop').click()")
assert "document.getElementById('streamHint')" in released
assert "busy === false && activeChatId === null" in released
assert "Частичный ответ не сохранён" in released
assert 'NOX_WEBVIEW2_STOP_OWNER_NOT_RELEASED_HOLD' in selftest
assert selftest.index('Native STOP was not confirmed') < selftest.index('WaitForStopUiReleaseAsync(TimeSpan.FromSeconds(4))') < selftest.index('checks["real_webview_stop_cancel_no_partial_persistence"] = "PASS"')
print('B04 R8 SOURCE_ONLY: live WebView2 token and STOP unlock acceptance oracle present (physical E2E NOT RUN)')

# B04 recovery: successful STOP is insufficient unless the same executable
# can accept the next real Qwen request and commit a new SQLite chat row.
assert 'int resumeTarget = Volatile.Read(ref generationStartedCount) + 1;' in selftest
assert 'NOX_CHAT_AFTER_STOP_START_HOLD' in selftest
assert 'NOX_CHAT_AFTER_STOP_SQLITE_HOLD' in selftest
assert 'checks["real_chat_after_http_stop_sqlite"] = "PASS";' in selftest
assert selftest.index('WaitForStopUiReleaseAsync(TimeSpan.FromSeconds(4))') < selftest.index('NOX_CHAT_AFTER_STOP_START_HOLD') < selftest.index('real_chat_after_http_stop_sqlite')
assert 'checks.Count == 6 && checks.Values.All(v => v == "PASS")' in selftest
assert 'if (resumeMarker != null) DeleteSyntheticChats(resumeMarker, null);' in selftest
print('B04 R8 SOURCE_ONLY: fresh chat after STOP and isolated SQLite cleanup gated (physical E2E NOT RUN)')



# D05 native task toggle: a checkbox is not proof of persistence.
# Request-ID bound receipt only after COMMIT and independent SQLite readback.
toggle = cs.split('private void HandleTaskToggle(', 1)[1].split('private static bool ValidWriteRequestId(', 1)[0]
assert 'ValidWriteRequestId(requestId)' in toggle
assert 'cmd.ExecuteNonQuery() != 1' in toggle
assert 'NOX_TASK_TOGGLE_MISSING_ROW_HOLD' in toggle
assert 'NOX_TASK_TOGGLE_SQLITE_READBACK_HOLD' in toggle
assert toggle.index('tx.Commit();') < toggle.index('using (var verifyDb = OpenDatabase())') < toggle.index('Send("tasks.toggle.receipt"')
assert 'Send("tasks.toggle.denied"' in toggle
assert 'case "tasks.toggle": HandleTaskToggle(request.GetProperty("id").GetInt64(), Text("requestId"));' in cs
for fragment in (
    "pendingTaskToggle={requestId,id:x.id,previous:x.complete}",
    "post('tasks.toggle',{id:x.id,requestId})",
    "case 'tasks.toggle.receipt':",
    "case 'tasks.toggle.denied':",
    "v?.requestId===pendingTaskToggle.requestId&&v?.id===pendingTaskToggle.id",
    "post('tasks.list')",
):
    assert fragment in html, 'D05_TOGGLE_OWNER_ACK_HOLD: '+fragment
# The SQL applies an actual toggle to precisely one row and refuses a missing row.
import sqlite3
with sqlite3.connect(':memory:') as db:
    db.execute('CREATE TABLE tasks(id INTEGER PRIMARY KEY, complete INTEGER NOT NULL DEFAULT 0)')
    db.execute('INSERT INTO tasks(id, complete) VALUES(42,0)')
    statement = "UPDATE tasks SET complete=CASE WHEN complete=0 THEN 1 ELSE 0 END WHERE id=?"
    assert db.execute(statement,(42,)).rowcount==1
    assert db.execute('SELECT complete FROM tasks WHERE id=42').fetchone()[0]==1
    assert db.execute(statement,(42,)).rowcount==1
    assert db.execute('SELECT complete FROM tasks WHERE id=42').fetchone()[0]==0
    assert db.execute(statement,(404,)).rowcount==0
print('D05 R8 SOURCE_ONLY: owner-correlated task toggle, SQLite COMMIT/readback and denied rollback PASS')

# B04: a previous successful chat must not leave a stale "saved" banner
# while a new prompt is generating or when that prompt terminates with error.
# This is an actual UI contract check; it is NOT physical owner-PC E2E.
send_section = html.split("$('send').onclick=()=>", 1)[1].split("\n$('stop').onclick=", 1)[0]
assert "busy=true;activeChatId=requestId;lastAnswer='';$('streamHint').textContent='Генерация ответа · не сохранено';" in send_section, 'B04_STALE_SQLITE_SUCCESS_DURING_GENERATION_HOLD'
complete_section = html.split("case 'complete':", 1)[1].split("break;", 1)[0]
assert "else if(v?.ok)$('streamHint').textContent='Ответ завершён и сохранён в SQLite.'" in complete_section
assert "else{$('streamHint').textContent='Ответ не сохранён в SQLite.';lastAnswer='';}" in complete_section, 'B04_STALE_SQLITE_SUCCESS_ON_ERROR_HOLD'
assert "if(v?.stopped){lastAnswer='';$('streamHint').textContent='Поток остановлен. Частичный ответ не сохранён.';}" in complete_section
print("B04 R8 SOURCE_ONLY: no stale SQLite saved banner during in-flight/error/STOP chat (Windows E2E NOT RUN)")
