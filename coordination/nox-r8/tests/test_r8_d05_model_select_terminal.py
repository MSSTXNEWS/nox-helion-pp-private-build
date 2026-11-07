"""D05 source contract only; NOT a physical Windows or owner-PC test."""
from pathlib import Path

source = (Path(__file__).resolve().parent / "src" / "MainWindow.xaml.cs").read_text(encoding="utf-8")
start = source.index("private async Task HandleModelSelect(")
end = source.index("private async Task SelectModel(", start)
handler = source[start:end]
begin = source.index("private async Task SelectModel(", end)
finish = source.index("private async Task PullExistingProviderModel(", begin)
selector = source[begin:finish]

# SQLite commit plus independent readback precede the terminal owner receipt.
assert handler.index("await SelectModel(model);") < handler.index('Send("model.select.receipt"')
assert 'try { Send("model.select.receipt", new { requestId, model, saved = true }); }' in handler
assert 'catch (Exception) { /* Persisted model remains authoritative; owner may refresh. */ }' in handler
assert 'NOX_MODEL_SELECT_PROVIDER_OR_SQLITE_HOLD' in handler

# A disconnected Ollama cannot strand MODEL SAVE behind the 10-minute client timeout.
assert 'new CancellationTokenSource(TimeSpan.FromSeconds(4))' in selector
assert 'http.GetAsync(Api + "/api/tags", probe.Token)' in selector
assert 'NOX_MODEL_SELECT_LEARN_CONSENT_HOLD' in selector
assert 'NOX_MODEL_SELECT_SQLITE_READBACK_HOLD' in selector
print("D05 MODEL SELECT SOURCE_ONLY PASS; owner Windows E2E NOT TESTED")
