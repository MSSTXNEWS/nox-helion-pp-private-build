"""R8 D05 feedback owner/Persona/readback structural regression. SOURCE_ONLY."""
from pathlib import Path
base = Path(__file__).resolve().parents[1] / "overrides" / "src"
c = (base / "MainWindow.xaml.cs").read_text(encoding="utf-8")
h = (base / "index.html").read_text(encoding="utf-8")
assert 'case "feedback": HandleFeedback(request);' in c
assert 'private long PersistChat(' in c and 'savedChatId = PersistChat(' in c
assert 'chatId = savedChatId, persona' in c
f = c.split('private void HandleFeedback(JsonElement request)',1)[1].split('// B04: switch only',1)[0]
assert 'ValidWriteRequestId(requestId)' in f and 'ActivePersona()' in f
assert 'seenFeedbackIds.Add(requestId)' in f
assert f.index('WHERE id=$id AND persona=$persona') < f.index('INSERT INTO feedback') < f.index('commitAttempted = true;') < f.index('tx.Commit();') < f.index('using (var verifyDb = OpenDatabase())') < f.index('Send("feedback.receipt"')
assert 'NOX_FEEDBACK_COMMIT_UNKNOWN_HOLD' in f and 'Send("feedback.uncertain"' in f
assert "post('feedback',{requestId,chatId,persona,rating})" in h
assert "case 'feedback.receipt':" in h and "case 'feedback.uncertain':" in h
assert 'retry?.persona===visibleDraftPersona' in h and 'Number.isSafeInteger(v?.chatId)' in h
assert "if(lastAnswer)post('feedback'" not in h
print('D05 feedback owner source contract PASS; native Windows acceptance NOT RUN')
