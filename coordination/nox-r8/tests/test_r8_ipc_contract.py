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
snapshot = cs.split('private string CheckpointSqlite(', 1)[1].split('private static bool HasPersonaColumn(', 1)[0]
assert snapshot.count('Pooling = false') == 2, 'B02_SQLITE_BACKUP_POOLING_HOLD'
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

# D05 MODEL SELECT: native owner-correlated choice requires independent SQLite
# readback before success ACK. A failed bridge keeps a retryable button.
assert 'case "model.select": await HandleModelSelect(Text("model"), Text("requestId")); break;' in cs, "D05_MODEL_NATIVE_ROUTE_HOLD"
model_handler = cs.split('private async Task HandleModelSelect(',1)[1].split('private async Task SelectModel(',1)[0]
model_select = cs.split('private async Task SelectModel(',1)[1].split('private async Task PullExistingProviderModel(',1)[0]
assert model_handler.index('ValidWriteRequestId(requestId)') < model_handler.index('await SelectModel(model);'), "D05_MODEL_OWNER_REQUEST_HOLD"
assert model_handler.index('await SelectModel(model);') < model_handler.index('Send("model.select.receipt"'), "D05_MODEL_PREMATURE_ACK_HOLD"
assert 'Send("model.select.denied"' in model_handler, "D05_MODEL_DENIAL_HOLD"
assert model_select.index('cmd.ExecuteNonQuery() != 1') < model_select.index('using (var verifyDb = OpenDatabase())'), "D05_MODEL_SQLITE_ACK_ORDER_HOLD"
assert 'Send("settings",ReadPreferences())' not in model_select, "D05_MODEL_REFRESH_BEFORE_ACK_HOLD"
assert model_handler.index('Send("model.select.receipt"') < model_handler.index('await CheckProvider();'), "D05_MODEL_ACK_REFRESH_ORDER_HOLD"
assert model_select.index("SELECT model FROM learn_requests WHERE owner_sid=$sid") < model_select.index("INSERT INTO preferences(key,value)"), "D05_MODEL_PENDING_CONSENT_ORDER_HOLD"
assert 'pending.Parameters.AddWithValue("$sid", OwnerSid());' in model_select, "D05_MODEL_SID_GUARD_HOLD"
assert 'NOX_MODEL_SELECT_LEARN_CONSENT_HOLD' in model_select and 'ex.Message == "NOX_MODEL_SELECT_LEARN_CONSENT_HOLD"' in model_handler, "D05_MODEL_CONSENT_DENIAL_HOLD"
assert "SELECT value FROM preferences WHERE key='model'" in model_select and 'NOX_MODEL_SELECT_SQLITE_READBACK_HOLD' in model_select, "D05_MODEL_SELECT_READBACK_HOLD"
for fragment in ("pendingModel={requestId,model}", "if(post('model.select',{model,requestId})===false)",
                 "v?.requestId===pendingModel.requestId&&v?.model===pendingModel.model",
                 "case 'model.select.receipt':", "case 'model.select.denied':",
                 "pendingModel=null;$('saveModel').disabled=false"):
    assert fragment in html, "D05_MODEL_WEBVIEW_OWNER_ACK_HOLD " + fragment
assert "post('model.select',{model});" not in html, "D05_MODEL_UNOWNED_DISPATCH_HOLD"
print('D05 R8 MODEL SELECT SOURCE_ONLY: native owner request/SQLite readback/ack/denial PASS; owner Windows NOT_TESTED')

# D05 NOTE DELETE NO-LOSS: independent SQLite readback after an actual owner
# confirmation and verified SHA snapshot, with exact WebView2 request ID.
note_delete = cs.split('private void HandleNoteDelete(',1)[1].split('private void SaveFeedback(',1)[0]
for marker in ('ValidWriteRequestId(requestId)', 'selfTestRequested', 'MessageBoxButton.YesNo',
               'MessageBoxResult.No', 'CheckpointSqlite(db, "PRE_NOTE_DELETE")',
               'DELETE FROM memory_notes WHERE id=$id AND persona=$persona',
               'Send("notes.delete.receipt"', 'Send("notes.delete.denied"'):
    assert marker in note_delete, 'D05_NOTE_DELETE_SAFETY_HOLD: '+marker
assert note_delete.index('MessageBox.Show') < note_delete.index('CheckpointSqlite(db, "PRE_NOTE_DELETE")') < note_delete.index('cmd.ExecuteNonQuery()') < note_delete.index('tx.Commit();') < note_delete.index('using (var readDb = OpenDatabase())') < note_delete.index('Send("notes.delete.receipt"'), 'D05_NOTE_DELETE_ACK_ORDER_HOLD'
assert 'case "notes.delete": HandleNoteDelete(' in cs
for marker in ("pendingNoteDelete={requestId,id:n.id,button:b}", "post('notes.delete',{id:n.id,requestId})", "case 'notes.delete.receipt':", "case 'notes.delete.denied':", "v?.requestId===pendingNoteDelete.requestId&&v?.id===pendingNoteDelete.id"):
    assert marker in html, 'D05_NOTE_DELETE_OWNER_UI_HOLD: '+marker
import sqlite3
with sqlite3.connect(':memory:') as conn:
    conn.execute('CREATE TABLE memory_notes(id INTEGER PRIMARY KEY, persona TEXT NOT NULL)')
    conn.executemany('INSERT INTO memory_notes(id,persona) VALUES(?,?)',[(10,'KV'),(20,'LA')])
    assert conn.execute('DELETE FROM memory_notes WHERE id=$id AND persona=$persona', {'id':20,'persona':'KV'}).rowcount == 0
    assert conn.execute('DELETE FROM memory_notes WHERE id=$id AND persona=$persona', {'id':10,'persona':'KV'}).rowcount == 1
    assert conn.execute('SELECT id FROM memory_notes').fetchall()==[(20,)]
print('D05 NOTE DELETE SOURCE_ONLY: consent, backup, owner Persona, commit/readback, request-ID receipt PASS')

# D05 MODEL PULL bounded STOP + exact-owner terminal receipts, SOURCE_ONLY.
pull = cs.split('private async Task PullExistingProviderModel(', 1)[1].split('private void ImportVuneoByConsent(', 1)[0]
assert 'case "model.pull": await PullExistingProviderModel(Text("model"), Text("requestId")); break;' in cs
assert 'string.Equals(activeModelPullRequestId, Text("requestId"), StringComparison.Ordinal)' in cs
assert pull.index('ValidWriteRequestId(requestId)') < pull.index('activeModelPull = cts;')
assert 'CancelAfter(TimeSpan.FromMinutes(3))' in pull and 'ReadLineAsync(idleTimeout.Token)' in pull
assert pull.index('if (!done)') < pull.index('GetAsync(Api + "/api/tags"') < pull.index('if (!installed)') < pull.index('status = "DONE"')
assert 'status = "STOPPED"' in pull and 'status = "TIMEOUT_HOLD"' in pull and 'status = "FAILED_HOLD"' in pull
assert 'ReferenceEquals(activeModelPull, cts)' in pull and 'activeModelPullRequestId = null;' in pull
assert "post('model.pull',{model,requestId})" in html and "post('model.cancel',{requestId:pendingDownload.requestId})" in html
assert "v?.requestId!==pendingDownload.requestId||v?.model!==pendingDownload.model" in html
assert "if(v.terminal===true)" in html and "const done=v.status==='DONE'" in html
assert "post('model.pull',{model})" not in html and "post('model.cancel');" not in html
print('D05 MODEL PULL SOURCE_ONLY: owner STOP, timeout, installed-tag readback and terminal GUI receipts PASS')
