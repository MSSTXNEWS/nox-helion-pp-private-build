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
    'Browser.CoreWebView2.NavigationStarting += (_, args) =>',
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
# Navigation must revoke the active WebView2 chat owner and invalidate
# every asynchronous provider-health callback from the previous document.
# Do not regress the native code to the obsolete one-line source contract.
# One trusted startup navigation, never a second untrusted document.
# Denied attempts (including about:blank) must not cancel native STOP/chat.
assert cs.count('Browser.CoreWebView2.NavigationStarting +=') == 1, 'B02_NAV_SINGLE_OWNER_HOLD'
nav = cs.split('Browser.CoreWebView2.NavigationStarting += (_, args) =>', 1)[1].split('\n            };', 1)[0]
assert 'if (pendingEmbeddedNavigation)' in nav, 'B02_NAV_STARTUP_GATE_HOLD'
assert 'pendingEmbeddedNavigation = false;' in nav, 'B02_NAV_ONE_SHOT_HOLD'
assert 'active?.Cancel();' in nav and 'activeRequestId = null;' in nav, 'B02_NAV_REVOKE_OWNER_HOLD'
assert 'Interlocked.Increment(ref providerProbeEpoch);' in nav, 'B02_NAV_REVOKE_PROBE_HOLD'
assert nav.index('if (pendingEmbeddedNavigation)') < nav.index('active?.Cancel();') < nav.index('activeRequestId = null;') < nav.index('Interlocked.Increment(ref providerProbeEpoch);') < nav.index('return;') < nav.index('args.Cancel = true;'), 'B02_NAV_TRUST_AND_OWNER_ORDER_HOLD'
assert 'if (!string.Equals(args.Uri, "about:blank"' not in nav, 'B02_NAV_ABOUT_BLANK_BYPASS_HOLD'
assert 'args.Cancel = true;' in nav, 'B02_NAV_DENY_ALL_FUTURE_HOLD'
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

# B02 WPF lifecycle: an in-flight native chat/health callback must never
# dispatch into WebView2 after owner window shutdown. Live failures stay visible.
send = cs.split('private void Send(string type, object value)', 1)[1].split('private async Task StartLocalEngine()', 1)[0]
assert send.count('providerProbeStopped || Dispatcher.HasShutdownStarted || Dispatcher.HasShutdownFinished') == 2, 'B02_SEND_SHUTDOWN_EPOCH_HOLD'
assert send.index('providerProbeStopped || Dispatcher.HasShutdownStarted') < send.index('JsonSerializer.Serialize'), 'B02_SEND_PRE_SERIALIZE_HOLD'
assert 'if (Dispatcher.CheckAccess()) PostIfAlive();' in send, 'B02_SEND_UI_OWNER_HOLD'
assert 'else Dispatcher.Invoke((Action)PostIfAlive);' in send, 'B02_SEND_DISPATCH_HOLD'
assert 'Browser.CoreWebView2?.PostWebMessageAsJson(data);' in send, 'B02_SEND_WEBVIEW_HOLD'
assert 'catch (ObjectDisposedException) when (providerProbeStopped)' in send, 'B02_SEND_DISPOSED_HOLD'
assert 'catch (OperationCanceledException) when (providerProbeStopped || Dispatcher.HasShutdownStarted)' in send, 'B02_SEND_CANCEL_SCOPE_HOLD'
assert 'catch (InvalidOperationException) when (providerProbeStopped || Dispatcher.HasShutdownStarted)' in send, 'B02_SEND_FAILURE_SCOPE_HOLD'
assert 'active?.Cancel(); activeModelPull?.Cancel(); http.Dispose();' in cs, 'B02_STOP_SHUTDOWN_HOLD'
print('B02 R8 SOURCE_ONLY: shutdown-only WebView2 dispatch suppression, live failures preserved')

# B02 R8 same-source provider restart integration: SOURCE_ONLY (not owner-PC E2E).
# A stream failure must terminate its exact request before bounded health refresh;
# only an explicit owner command may start the already-installed service.
startup = cs.split('private async Task StartLocalEngine()', 1)[1].split('private async Task CheckProvider()', 1)[0]
probe = cs.split('private async Task CheckProvider()', 1)[1].split('private async Task Generate(', 1)[0]
chat = cs.split('private async Task Generate(', 1)[1].split('private void PersistChat(', 1)[0]
assert 'private readonly SemaphoreSlim engineStartLock = new(1, 1);' in cs, 'B02_OWNER_LOCK_MISSING_HOLD'
assert 'if (!engineStartLock.Wait(0))' in startup, 'B02_DUPLICATE_LAUNCH_HOLD'
assert startup.count('Process.Start(ps)') == 1, 'B02_MULTIPLE_SPAWNS_HOLD'
assert startup.index('engineStartLock.Wait(0)') < startup.index('GetActiveTcpListeners()') < startup.index('Process.Start(ps)'), 'B02_START_LOCK_ORDER_HOLD'
assert 'finally {\n            engineStartLock.Release();' in startup, 'B02_OWNER_LOCK_RELEASE_HOLD'
assert 'ps.Environment["OLLAMA_HOST"] = "127.0.0.1:11436";' in startup, 'B02_PROVIDER_ENDPOINT_HOLD'
assert 'ps.Environment["OLLAMA_MODELS"] = modelDir;' in startup, 'B02_EXISTING_MODELS_HOLD'
# Owner-triggered provider recovery must surface failure in the existing
# engine notice, not as an unrelated chat error, and refresh actual health.
# Do not catch arbitrary internal failures or claim recovery without a probe.
assert 'LOCAL_PROVIDER_START_FAILED:' in startup, 'B02_ENGINE_FAILURE_NOTICE_HOLD'
assert 'Send("notice", "LOCAL_PROVIDER_START_FAILED: " + ex.Message);' in startup, 'B02_ENGINE_FAILURE_WRONG_CHANNEL_HOLD'
assert 'catch (Exception ex) when (!providerProbeStopped &&' in startup, 'B02_ENGINE_FAILURE_SHUTDOWN_GUARD_HOLD'
assert all(exc in startup for exc in ('ex is InvalidOperationException', 'ex is System.ComponentModel.Win32Exception', 'ex is UnauthorizedAccessException', 'ex is IOException', 'ex is HttpRequestException', 'ex is OperationCanceledException')), 'B02_ENGINE_FAILURE_EXPECTED_ERRORS_HOLD'
assert startup.index('Send("notice", "LOCAL_PROVIDER_START_FAILED: "') < startup.rindex('await CheckProvider();') < startup.index('engineStartLock.Release();'), 'B02_ENGINE_FAILURE_HEALTH_ORDER_HOLD'
assert startup.count('Process.Start(ps)') == 1, 'B02_ENGINE_FAILURE_NO_DUPLICATE_SPAWN_HOLD'

assert 'TimeSpan.FromSeconds(25)' in cs, 'B02_REATTACH_INTERVAL_HOLD'
assert 'if (!selfTestRequested && !providerReconnectTimer.IsEnabled)' in cs, 'B02_REATTACH_SELFTEST_HOLD'
assert 'providerReconnectTimer.Stop();' in cs, 'B02_REATTACH_SHUTDOWN_HOLD'
assert 'Interlocked.Increment(ref providerProbeEpoch);' in cs, 'B02_STALE_WEBVIEW_PROBE_HOLD'
assert probe.count('probeEpoch == Volatile.Read(ref providerProbeEpoch)') == 2, 'B02_REATTACH_EPOCH_HOLD'
assert probe.count('active == null') == 2, 'B02_HEALTH_OWNERSHIP_HOLD'
assert 'http.GetAsync(Api + "/api/tags", probe.Token)' in probe, 'B02_PROVIDER_LOOPBACK_HOLD'
assert 'Process.Start(' not in probe, 'B02_HEALTH_MUST_NOT_SPAWN_HOLD'
assert 'bool refreshProviderAfterError = false;' in chat, 'B02_ERROR_REFRESH_FLAG_HOLD'
assert 'await CheckProvider();' not in chat.split('catch (HttpRequestException ex) {',1)[1].split('catch (Exception ex) {',1)[0], 'B02_PREMATURE_HEALTH_HOLD'
assert chat.index('Emit("complete", new { requestId, ok = false, stopped = false });', chat.index('catch (HttpRequestException ex)')) < chat.index('generationLock.Release();') < chat.rindex('await CheckProvider();'), 'B02_TERMINAL_BEFORE_HEALTH_HOLD'
print('B02 R8 SOURCE_ONLY PASS: single-flight owner startup, bounded reattach, terminal IPC and STOP isolation (Windows/owner E2E NOT_TESTED)')

# A replayed chat requestId must NOT issue a premature terminal ACK:
# it would unlock the current WebView2 chat while the real owner still streams.
# New distinct busy requestIds retain their request-correlated rejection ACK.
duplicate_busy = generate.split('if (!await generationLock.WaitAsync(0)) {', 1)[1].split('using var cancellation = new CancellationTokenSource();', 1)[0]
assert 'if (string.Equals(activeRequestId, requestId, StringComparison.Ordinal))' in duplicate_busy, 'B02_DUPLICATE_CHAT_OWNER_GUARD_HOLD'
assert re.search(r'if \(string\.Equals\(activeRequestId, requestId, StringComparison\.Ordinal\)\)\s*return;', duplicate_busy), 'B02_DUPLICATE_CHAT_MUST_NOT_COMPLETE_HOLD'
assert duplicate_busy.index('return;') < duplicate_busy.index('RejectChat("CHAT_ALREADY_RUNNING_HOLD");'), 'B02_DUPLICATE_CHAT_EARLY_RETURN_HOLD'
assert duplicate_busy.count('RejectChat("CHAT_ALREADY_RUNNING_HOLD");') == 1, 'B02_DISTINCT_CHAT_REJECT_HOLD'

# B02: Once a native chat request finishes (success/STOP/offline), a delayed
# replay with the same requestId must not start another Qwen request / SQLite row.
# The process-local bounded cache is a SOURCE_ONLY guard, not runtime evidence.
replay = generate.split('if (!await generationLock.WaitAsync(0)) {', 1)[0]
assert 'recentlyHandledChatIdSet.Contains(requestId)' in replay, 'B02_TERMINAL_CHAT_REPLAY_HOLD'
assert replay.index('recentlyHandledChatIdSet.Contains(requestId)') < replay.index('if (!await generationLock.WaitAsync(0)) {') if 'if (!await generationLock.WaitAsync(0)) {' in replay else True
assert 'RejectChat("CHAT_REPLAY_AFTER_TERMINAL_DENIED");' in replay, 'B02_REPLAY_TERMINAL_DENIAL_HOLD'
assert 'private readonly HashSet<string> recentlyHandledChatIdSet = new(StringComparer.Ordinal);' in cs, 'B02_REPLAY_OWNER_SET_HOLD'
assert 'private readonly Queue<string> recentlyHandledChatIds = new();' in cs, 'B02_REPLAY_QUEUE_HOLD'
terminal = generate.split('finally {', 1)[1].split('generationLock.Release();', 1)[0]
assert 'recentlyHandledChatIdSet.Add(requestId)' in terminal, 'B02_REMEMBER_TERMINAL_ID_HOLD'
assert 'recentlyHandledChatIds.Count > 128' in terminal, 'B02_REPLAY_MEMORY_BOUND_HOLD'
assert terminal.index('recentlyHandledChatIdSet.Add(requestId)') < terminal.index('activeRequestId = null;'), 'B02_TERMINAL_CACHE_BEFORE_OWNER_RELEASE_HOLD'
print('B02 R8 SOURCE_ONLY: delayed terminal owner replay blocked, bounded to 128 process IDs; Windows E2E NOT_TESTED')


# B02 native IPC JSON ambiguity: JsonDocument.GetProperty otherwise returns
# the last duplicate field, potentially changing type/requestId after dispatch.
# Reject duplicate names at any object depth and bound message size before
# native actions, while preserving all existing routes and owner-correlated STOP.
ipc_guard = cs.split('private static bool HasDuplicateJsonProperties(JsonElement element)', 1)[1].split('private async void OnMessage(', 1)[0]
message = cs.split('private async void OnMessage(', 1)[1].split('private void Send(', 1)[0]
assert 'new HashSet<string>(StringComparer.Ordinal)' in ipc_guard, 'B02_DUPLICATE_ORDINAL_DENY_HOLD'
assert 'element.ValueKind == JsonValueKind.Object' in ipc_guard, 'B02_DUPLICATE_OBJECT_WALK_HOLD'
assert '!names.Add(property.Name) || HasDuplicateJsonProperties(property.Value)' in ipc_guard, 'B02_DUPLICATE_NESTED_WALK_HOLD'
assert 'element.ValueKind == JsonValueKind.Array' in ipc_guard, 'B02_DUPLICATE_ARRAY_WALK_HOLD'
assert 'HasDuplicateJsonProperties(item)' in ipc_guard, 'B02_DUPLICATE_ARRAY_RECURSE_HOLD'
assert 'rawMessage.Length > 512 * 1024' in message, 'B02_WEBMESSAGE_SIZE_BOUND_HOLD'
assert 'NOX_IPC_MESSAGE_TOO_LARGE_DENIED' in message, 'B02_MESSAGE_BOUND_DENIED_HOLD'
assert 'request.ValueKind != JsonValueKind.Object || HasDuplicateJsonProperties(request)' in message, 'B02_IPC_ROOT_DUPLICATE_DENIED_HOLD'
assert 'NOX_IPC_AMBIGUOUS_JSON_DENIED' in message, 'B02_IPC_AMBIGUOUS_DENIED_HOLD'
assert message.index('rawMessage.Length > 512 * 1024') < message.index('JsonDocument.Parse(rawMessage)') < message.index('HasDuplicateJsonProperties(request)') < message.index('var kind = request.GetProperty("type")') < message.index('switch (kind)'), 'B02_IPC_FAIL_CLOSED_ORDER_HOLD'
print('B02 R8 SOURCE_ONLY: bounded duplicate-free native IPC before command dispatch; Windows Qwen NOT_TESTED')
