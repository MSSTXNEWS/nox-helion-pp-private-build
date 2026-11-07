"""R8 native IPC/STOP/provider source regression. SOURCE_ONLY, never owner-PC acceptance."""
from pathlib import Path
import subprocess
import shutil
import re

root = Path(__file__).resolve().parent
# F02: one layout per trusted source origin, never an automatic stale fallback.
if root.name == "tests" and root.parent.name == "nox-r8":
    source_dir = root.parent / "overrides" / "src"
elif root.name == "r8":
    source_dir = root / "src"
else:
    raise AssertionError("F02_IPC_SQLITE_TEST_ORIGIN_HOLD")
for name in ("MainWindow.xaml.cs", "index.html"):
    assert (source_dir / name).is_file(), "F02_IPC_SQLITE_SOURCE_MISSING_HOLD: " + str(source_dir / name)
cs = (source_dir / "MainWindow.xaml.cs").read_text(encoding="utf-8")
html = (source_dir / "index.html").read_text(encoding="utf-8")
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
    "case 'token':if(pendingChatDraft?.persona!==visibleDraftPersona)break;lastAnswer+=v.text",
    "case 'complete':{const retry=pendingChatDraft?.requestId===v?.requestId",
    "Only the matching native complete may unlock a busy chat.",
    "if(e.key==='Escape'&&busy&&activeChatId){e.preventDefault();$('stop').click();return;}",
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
# F02: assert original receiving handler guards owner ID before the switch.
# A literal token/STOP substring elsewhere is NOT sufficient proof.
receiver = html.split("window.chrome?.webview?.addEventListener('message',e=>{", 1)[1].split("\n});", 1)[0]
owner_filter = "if(['status','token','metrics','complete'].includes(m.type) && (!v || v.requestId!==activeChatId))return;"
assert receiver.count(owner_filter) == 1, 'F02_NATIVE_OWNER_FILTER_HOLD'
assert receiver.index(owner_filter) < receiver.index('switch(m.type){') < receiver.index("case 'token':"), 'F02_OWNER_FILTER_ORDER_HOLD'
token = receiver.split("case 'token':", 1)[1].split("case 'metrics':", 1)[0]
assert 'if(pendingChatDraft?.persona!==visibleDraftPersona)break;' in token, 'F02_CROSS_PERSONA_TOKEN_HOLD'
assert token.index('if(pendingChatDraft?.persona!==visibleDraftPersona)break;') < token.index('lastAnswer+=v.text'), 'F02_TOKEN_VISIBILITY_ORDER_HOLD'
# Keyboard path must actually call the already owner-bound STOP button.
keyboard = html.rsplit("document.addEventListener('keydown',e=>{", 1)[1].split("\n});", 1)[0]
key_guard = 'if(e.defaultPrevented||e.isComposing||e.keyCode===229||e.repeat)return;'
esc_stop = "if(e.key==='Escape'&&busy&&activeChatId){e.preventDefault();$('stop').click();return;}"
assert keyboard.count(key_guard) == 1 and keyboard.count(esc_stop) == 1, 'F02_ESCAPE_STOP_GUARD_HOLD'
assert keyboard.index(key_guard) < keyboard.index(esc_stop), 'F02_IME_STOP_ORDER_HOLD'
assert "post('stop',{requestId:activeChatId})" in html, 'F02_STOP_REQUEST_OWNER_HOLD'

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
# F01's real WAL writer negative control adds its own separately-unpooled
# readback. Keep the original two no-pooling handles mandatory and account
# for the extra isolated reader only when the native fixture is present.
expected_unpooled = 3 if "NOX_F01_WAL_UNCOMMITTED_VISIBLE_HOLD" in smoke_backup else 2
assert smoke_backup.count('Pooling = false') == expected_unpooled, 'B03_SMOKE_BACKUP_POOLING_HOLD'
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
assert (generate.index('cancellation.Token.ThrowIfCancellationRequested();', generate.index('if (!completed)')) <
        generate.index('sqliteWriteAttempted = true;') <
        generate.index('PersistChat(prompt, answer.ToString(), persona);') <
        generate.index('sqliteVerified = true;') <
        generate.index('Emit("complete", new { requestId, ok = answer.Length > 0')), 'B04_STOP_BEFORE_SQLITE_COMMIT_ORDER_HOLD'
assert 'bool sqliteUnknown = sqliteWriteAttempted && !sqliteVerified;' in generate
assert 'NOX_CHAT_SQLITE_COMMIT_UNKNOWN_HOLD' in generate
assert 'stopped = false, sqliteUnknown' in generate
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
    "pendingTask={requestId,text,persona:visibleDraftPersona}",
    "pendingNote={requestId,title,content,persona:visibleDraftPersona}",
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
assert "case 'complete':{const retry=pendingChatDraft?.requestId===v?.requestId" in html and "busy=false;activeChatId=null;" in html, 'B04_WEBVIEW_CHAT_UNLOCK_HOLD'
print('B04 R8 SOURCE_ONLY: native preflight rejection now releases the matching WebView2 owner')

# B04 live HTTP STOP acceptance regression: a task/HTTP POST beginning is not
# evidence of a real streaming response. The self-test must wait for an actual
# nonempty Ollama NDJSON token before pressing WebView2 STOP.
selftest = cs.split('private async Task RunNativeSelfTestAsync()', 1)[1].split('private bool HasSavedPrompt(', 1)[0]
token_wait = cs.split('private async Task<bool> WaitForGenerationTokenAsync(', 1)[1].split('private async Task WaitForGenerationFinishAsync(', 1)[0]
generation = cs.split('private async Task Generate(', 1)[1].split('private void PersistChat(', 1)[0]
assert 'int streamTokenTarget = Volatile.Read(ref generationStreamingTokenCount) + 2;' in selftest
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
assert 'checks.Count == 7 && checks.Values.All(v => v == "PASS")' in selftest
assert 'if (resumeMarker != null) DeleteSyntheticChats(resumeMarker, null);' in selftest
print('B04 R8 SOURCE_ONLY: fresh chat after STOP and isolated SQLite cleanup gated (physical E2E NOT RUN)')



# D05 native task toggle: a checkbox is not proof of persistence.
# Request-ID bound receipt only after COMMIT and independent SQLite readback.
toggle = cs.split('private void HandleTaskToggle(', 1)[1].split('private static bool ValidWriteRequestId(', 1)[0]
assert 'ValidWriteRequestId(requestId)' in toggle
assert 'cmd.ExecuteNonQuery() != 1' in toggle
assert 'NOX_TASK_TOGGLE_MISSING_ROW_HOLD' in toggle
assert 'NOX_TASK_TOGGLE_SQLITE_READBACK_HOLD' in toggle
assert toggle.index('tx.Commit();') < toggle.index('using var verifyDb = OpenDatabase();') < toggle.index('Send("tasks.toggle.receipt"')
assert 'Send("tasks.toggle.denied"' in toggle
assert 'case "tasks.toggle": {' in cs and 'HandleTaskToggle(taskId, desiredComplete, Text("requestId"));' in cs
for fragment in (
    "pendingTaskToggle={requestId,id:x.id,previous:x.complete,target:cb.checked}",
    "post('tasks.toggle',{id:x.id,complete:cb.checked,requestId})",
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
    statement = "UPDATE tasks SET complete=? WHERE id=?"
    assert db.execute(statement,(1,42)).rowcount==1
    assert db.execute('SELECT complete FROM tasks WHERE id=42').fetchone()[0]==1
    assert db.execute(statement,(1,42)).rowcount==1
    assert db.execute('SELECT complete FROM tasks WHERE id=42').fetchone()[0]==1
    assert db.execute(statement,(1,404)).rowcount==0
print('D05 R8 SOURCE_ONLY: owner-correlated task toggle, SQLite COMMIT/readback and denied rollback PASS')

# B04: a previous successful chat must not leave a stale "saved" banner
# while a new prompt is generating or when that prompt terminates with error.
# This is an actual UI contract check; it is NOT physical owner-PC E2E.
send_section = html.split("$('send').onclick=()=>", 1)[1].split("\n$('stop').onclick=", 1)[0]
assert "busy=true;activeChatId=requestId;pendingChatDraft={requestId,raw:$('prompt').value,persona:visibleDraftPersona};lastAnswer='';$('streamHint').textContent='Генерация ответа · не сохранено';" in send_section, 'B04_STALE_SQLITE_SUCCESS_DURING_GENERATION_HOLD'
complete_section = html.split("case 'complete':", 1)[1].split("break;", 1)[0]
assert "else if(v?.ok)$('streamHint').textContent='Ответ завершён и сохранён в SQLite.'" in complete_section
assert "else{lastAnswer='';$('streamHint').textContent='Ответ не сохранён.'" in complete_section, 'B04_STALE_SQLITE_SUCCESS_ON_ERROR_HOLD'
assert "if(v?.stopped){lastAnswer='';$('streamHint').textContent='Поток остановлен. Частичный ответ не сохранён.'" in complete_section
print("B04 R8 SOURCE_ONLY: no stale SQLite saved banner during in-flight/error/STOP chat (Windows E2E NOT RUN)")

# B04 acceptance race: native generationFinishedCount may be published before
# WebView2 has processed complete. The next SEND must await the DOM owner ACK.
# Existing UI/transport production code is intentionally untouched.
native_test = cs.split('private async Task RunNativeSelfTestAsync()', 1)[1].split('private bool HasSavedPrompt(', 1)[0]
saved_ack = cs.split('private async Task<bool> WaitForSavedChatUiReleaseAsync(', 1)[1].split('private async Task WaitForGenerationFinishAsync(', 1)[0]
assert native_test.count('WaitForSavedChatUiReleaseAsync(TimeSpan.FromSeconds(4))') == 2, 'B04_CHAT_UI_RELEASE_ACK_COUNT_HOLD'
assert native_test.index('NOX_WEBVIEW2_FIRST_CHAT_OWNER_NOT_RELEASED_HOLD') < native_test.index('int streamTokenTarget'), 'B04_FIRST_CHAT_UI_OWNER_RACE_HOLD'
assert native_test.index('NOX_WEBVIEW2_RESUMED_CHAT_OWNER_NOT_RELEASED_HOLD') < native_test.index('checks["real_chat_after_http_stop_sqlite"] = "PASS"'), 'B04_RESUMED_CHAT_UI_OWNER_HOLD'
for fragment in ('busy === false', 'activeChatId === null', "indicator?.classList.contains('on') === false", "hint?.textContent === 'Ответ завершён и сохранён в SQLite.'"):
    assert fragment in saved_ack, 'B04_CHAT_UI_RELEASE_ACK_INCOMPLETE_HOLD: '+fragment
assert 'if (released == "true") return true;' in saved_ack and 'return false;' in saved_ack
print('B04 R8 SOURCE_ONLY: WebView2 terminal ACK gate before next SEND and after resumed Qwen chat; Windows E2E NOT_RUN')

# B02 WPF lifecycle: an in-flight native chat/health callback must never
# dispatch into WebView2 after owner window shutdown. Live failures stay visible.
send = cs.split('private void Send(string type, object value)', 1)[1].split('private async Task StartLocalEngine(CancellationToken stopToken = default)', 1)[0]
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
# startup/owner/chat may reuse the single already-installed local engine.
startup = cs.split('private async Task StartLocalEngine(CancellationToken stopToken = default)', 1)[1].split('private async Task CheckProvider()', 1)[0]
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
owner_start = startup.split('private async Task RecoverLocalEngineAtStartupAsync()', 1)[0]
assert owner_start.index('Send("notice", "LOCAL_PROVIDER_START_FAILED: "') < owner_start.index('await CheckProvider();') < owner_start.index('engineStartLock.Release();'), 'B02_ENGINE_FAILURE_HEALTH_ORDER_HOLD'
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

# B02 active-owner replay before all preflight RejectChat, including empty/huge inputs.
pre_validation = generate.split('if (string.IsNullOrWhiteSpace(prompt))', 1)[0]
assert re.search(r'if \(active != null && string\.Equals\(activeRequestId, requestId, StringComparison\.Ordinal\)\)\s*return;', pre_validation), 'B02_SAME_OWNER_REPLAY_BEFORE_VALIDATION_HOLD'
assert pre_validation.index('if (active != null && string.Equals(activeRequestId, requestId, StringComparison.Ordinal))') > pre_validation.index('void RejectChat(string reason)'), 'B02_ACTIVE_OWNER_REPLAY_POSITION_HOLD'
assert generate.index('if (active != null && string.Equals(activeRequestId, requestId, StringComparison.Ordinal))') < generate.index('CHAT_EMPTY_PROMPT_DENIED') < generate.index('CHAT_REQUEST_ID_DENIED') < generate.index('CHAT_PROMPT_TOO_LONG_DENIED'), 'B02_SAME_OWNER_NO_PREMATURE_ACK_HOLD'

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


# B02 native Ollama provider-restart corner case: a valid HTTP response can
# fail during NDJSON consumption with IOException/JsonException or EOF before
# done=true. Never mislabel SQLite failures or owner STOP as provider loss.
# Re-probe actual /api/tags only after request-correlated terminal ACK and lock release.
provider_recovery = cs.split('private async Task Generate(', 1)[1].split('private void PersistChat(', 1)[0]
assert 'bool providerStreamRequested = false;' in provider_recovery, 'B02_STREAM_REQUEST_TRACK_HOLD'
assert provider_recovery.index('providerStreamRequested = true;') < provider_recovery.index('await http.SendAsync('), 'B02_STREAM_REQUEST_BEFORE_HTTP_HOLD'
broken_eof = provider_recovery.split('if (!completed) {', 1)[1].split('// A STOP received with the final token', 1)[0]
assert 'refreshProviderAfterError = true;' in broken_eof and 'throw new InvalidOperationException(' in broken_eof, 'B02_STREAM_EOF_HEALTH_REFRESH_HOLD'
generic_error = provider_recovery.split('catch (Exception ex) {', 1)[1].split('finally {', 1)[0]
assert 'providerStreamRequested && (ex is IOException || ex is JsonException)' in generic_error, 'B02_STREAM_TRANSPORT_ERRORS_HOLD'
assert 'refreshProviderAfterError = true;' in generic_error, 'B02_STREAM_TRANSPORT_RECHECK_HOLD'
assert generic_error.index('refreshProviderAfterError = true;') < generic_error.index('Emit("complete", new { requestId, ok = sqliteVerified, stopped = false, sqliteUnknown });'), 'B02_STREAM_COMPLETE_ORDER_HOLD'
assert 'bool sqliteUnknown = sqliteWriteAttempted && !sqliteVerified;' in generic_error, 'B02_SQLITE_UNKNOWN_OUTCOME_HOLD'
assert provider_recovery.index('Emit("complete", new { requestId, ok = sqliteVerified, stopped = false, sqliteUnknown });',provider_recovery.index('catch (Exception ex) {')) < provider_recovery.index('generationLock.Release();') < provider_recovery.rindex('await CheckProvider();'), 'B02_STREAM_TERMINAL_BEFORE_HEALTH_HOLD'
assert 'providerStreamRequested && (ex is IOException || ex is JsonException)' not in provider_recovery.split('catch (OperationCanceledException) when (cancellation.IsCancellationRequested)', 1)[1].split('catch (OperationCanceledException) {',1)[0], 'B02_STREAM_STOP_ISOLATION_HOLD'
print('B02 R8 SOURCE_ONLY: truncated/invalid Ollama NDJSON triggers real health re-probe after terminal ACK; owner STOP and SQLite preserved')


# B02 reconciliation with canonical R8 recovery source (2026-11-07).
# SOURCE_ONLY, not evidence of compiled Windows EXE or local Ollama inference.
startup = cs.split('private async Task StartLocalEngine(CancellationToken stopToken = default)', 1)[1].split('private async Task CheckProvider()', 1)[0]
generate = cs.split('private async Task Generate(', 1)[1].split('private void PersistChat(', 1)[0]
navigate = cs.split('Browser.CoreWebView2.NavigationCompleted +=', 1)[1].split('Browser.CoreWebView2.NavigationStarting +=', 1)[0]
assert 'if (!selfTestRequested) _ = RecoverLocalEngineAtStartupAsync();' in navigate, 'B02_R8_AUTO_STARTUP_RECOVERY_HOLD'
assert 'private async Task StartLocalEngineCore(CancellationToken stopToken)' in startup, 'B02_R8_SINGLE_PROVIDER_CORE_HOLD'
assert 'await engineStartLock.WaitAsync(stopToken);' in startup and 'if (!engineStartLock.Wait(0))' in startup, 'B02_R8_SINGLE_FLIGHT_OWNER_LOCK_HOLD'
assert 'await Task.Delay(1000, stopToken);' in startup, 'B02_R8_STOP_PROVIDER_START_WAIT_HOLD'
assert startup.index('stopToken.ThrowIfCancellationRequested();\n        var launched = Process.Start(ps);') < startup.index('await Task.Delay(1000, stopToken);') if 'stopToken.ThrowIfCancellationRequested();\n        var launched = Process.Start(ps);' in startup else startup.index('stopToken.ThrowIfCancellationRequested();', startup.index('ps.Environment["OLLAMA_MODELS"] = modelDir;')) < startup.index('var launched = Process.Start(ps);') < startup.index('await Task.Delay(1000, stopToken);'), 'B02_R8_STOP_BEFORE_SPAWN_HOLD'
assert 'if (stopToken.CanBeCanceled) throw;' in startup, 'B02_R8_GENERATION_TERMINAL_ERROR_HOLD'
assert 'LOCAL_PROVIDER_START_FAILED:' in startup and 'await CheckProvider();' in startup, 'B02_R8_OWNER_NOTICE_AFTER_START_ERROR_HOLD'
assert 'await StartLocalEngine(cancellation.Token);' in generate, 'B02_R8_CHAT_RECOVERY_HOLD'
assert 'probe.CancelAfter(TimeSpan.FromSeconds(5));' in generate and 'NOX_MODEL_NOT_REGISTERED:' in generate, 'B02_R8_MODEL_TAG_ADMISSION_HOLD'
assert generate.index('await StartLocalEngine(cancellation.Token);') < generate.index('NOX_MODEL_NOT_REGISTERED:') < generate.index('var persona = ActivePersona();') < generate.index('await http.SendAsync('), 'B02_R8_MODEL_PREHTTP_HOLD'
assert 'providerRecoveryPending || (providerStreamRequested &&' in generate, 'B02_R8_PROVIDER_START_HEALTH_REFRESH_HOLD'
assert 'catch (OperationCanceledException) when (stopToken.IsCancellationRequested)' in startup, 'B02_R8_STOP_NOT_SWALLOWED_HOLD'
print('B02 R8 SOURCE_ONLY: canonical startup + per-chat recovery, single-owner launch, cancellable STOP, registered model guard PASS; Windows NOT_TESTED')
# B06: source-only stream lifetime regression, not Windows E2E.
_budget = cs.split('private async Task Generate(',1)[1].split('private void PersistChat(',1)[0]
assert _budget.count('using var streamBudget = CancellationTokenSource.CreateLinkedTokenSource(cancellation.Token);') == 1, 'B06_LINKED_STREAM_BUDGET_HOLD'
assert _budget.count('streamBudget.CancelAfter(TimeSpan.FromMinutes(15));') == 1, 'B06_ABSOLUTE_STREAM_BUDGET_HOLD'
assert _budget.index('streamBudget.CancelAfter(TimeSpan.FromMinutes(15));') < _budget.index('while (true)'), 'B06_STREAM_BUDGET_BEFORE_READ_HOLD'
assert 'CancellationTokenSource.CreateLinkedTokenSource(streamBudget.Token)' in _budget, 'B06_PER_LINE_FROM_STREAM_BUDGET_HOLD'
assert 'readWindow.CancelAfter(TimeSpan.FromMinutes(3));' in _budget, 'B06_IDLE_GUARD_NO_LOSS_HOLD'
assert 'catch (OperationCanceledException) when (cancellation.IsCancellationRequested)' in _budget and 'OLLAMA_TIMEOUT:' in _budget, 'B06_OWNER_STOP_VS_TIMEOUT_HOLD'
print('B06 SOURCE_ONLY: total 15m stream + 3m idle, STOP distinct; real Qwen not tested')

# B04: real HTTP cancellation may surface as IOException, HttpRequestException or
# ObjectDisposedException, not just OperationCanceledException. This source-only
# oracle requires STOP after stream abort, but never masks an attempted COMMIT.
transport_guard = 'catch (Exception ex) when (cancellation.IsCancellationRequested && !sqliteWriteAttempted &&'
assert transport_guard in generate, 'B04_STOP_HTTP_IO_OWNER_HOLD'
transport_stop = generate.split(transport_guard, 1)[1].split('catch (HttpRequestException ex)', 1)[0]
for kind in ('HttpRequestException', 'IOException', 'ObjectDisposedException'):
    assert 'ex is ' + kind in transport_stop, 'B04_STOP_HTTP_' + kind + '_HOLD'
assert 'lastGenerationStopped = true;' in transport_stop, 'B04_STOP_IO_STATE_HOLD'
assert 'state = "STOPPED"' in transport_stop and 'stopped = true' in transport_stop, 'B04_STOP_IO_RECEIPT_HOLD'
assert generate.index(transport_guard) < generate.index('catch (HttpRequestException ex)'), 'B04_STOP_IO_CATCH_ORDER_HOLD'
print('B04 R8 STOP transport source oracle PASS; real owner Ollama NOT_TESTED')

# B02: cap cumulative streamed answer before emitting any oversized chunk.
# The original Qwen num_predict is not an enforced provider-side byte budget;
# a nonterminal stream that emits data indefinitely must not exhaust WebView2.
# This is SOURCE_ONLY, not a real Windows/Ollama stream acceptance.
_output_guard = cs.split('private async Task Generate(', 1)[1].split('private void PersistChat(', 1)[0]
_token_block = _output_guard.split('if (item.TryGetProperty("response", out var token))', 1)[1].split('if (item.TryGetProperty("error", out var serverError))', 1)[0]
assert _output_guard.count('const int MaxAnswerChars = 256 * 1024;') == 1, 'B02_OUTPUT_MAX_MISSING_HOLD'
assert 'if (value.Length > MaxAnswerChars - answer.Length)' in _token_block, 'B02_OUTPUT_CUMULATIVE_BUDGET_HOLD'
assert 'OLLAMA_RESPONSE_LIMIT_HOLD:' in _token_block, 'B02_OUTPUT_EXCEEDED_REASON_HOLD'
assert _token_block.index('if (value.Length > MaxAnswerChars - answer.Length)') < _token_block.index('answer.Append(value);') < _token_block.index('Emit("token", new { requestId, text = value });'), 'B02_OUTPUT_REJECT_BEFORE_APPEND_AND_IPC_HOLD'
assert _output_guard.index('if (value.Length > MaxAnswerChars - answer.Length)') < _output_guard.index('sqliteWriteAttempted = true;'), 'B02_OUTPUT_PRE_SQLITE_HOLD'
assert 'Emit("complete", new { requestId, ok = sqliteVerified, stopped = false, sqliteUnknown });' in _output_guard, 'B02_OUTPUT_TERMINAL_ACK_HOLD'
assert 'catch (OperationCanceledException) when (cancellation.IsCancellationRequested)' in _output_guard, 'B02_OUTPUT_STOP_PRESERVED_HOLD'
print('B02 SOURCE_ONLY: cumulative response cap rejects before append/IPC/SQLite; terminal ERROR/complete and owner STOP paths preserved; Windows NOT_TESTED')
