"""R8 real local provider autostart + user STOP admission (SOURCE_ONLY)."""
from pathlib import Path
src = Path(__file__).resolve().parent / "src" / "MainWindow.xaml.cs"
s = src.read_text(encoding="utf-8")
checks = [
    "private readonly SemaphoreSlim engineStartLock = new(1, 1);",
    "if (!selfTestRequested) _ = RecoverLocalEngineAtStartupAsync();",
    "private async Task StartLocalEngine(CancellationToken stopToken = default)",
    "await engineStartLock.WaitAsync(stopToken);",
    "finally { engineStartLock.Release(); }",
    "private async Task RecoverLocalEngineAtStartupAsync()",
    "private async Task StartLocalEngineCore(CancellationToken stopToken)",
    "stopToken.ThrowIfCancellationRequested();",
    "await Task.Delay(1000, stopToken);",
    "await StartLocalEngine(cancellation.Token);",
    "probe.CancelAfter(TimeSpan.FromSeconds(5));",
    "NOX_MODEL_NOT_REGISTERED:",
    'ps.Environment["OLLAMA_HOST"] = "127.0.0.1:11436";',
    'ps.Environment["OLLAMA_MODELS"] = modelDir;',
]
for value in checks:
    assert value in s, "TECHFIRST_PROVIDER_CONTRACT_MISSING: " + value
onload=s.split("private async Task Initialize()",1)[1].split("private async Task UiSmokeWatchdogAsync()",1)[0]
assert onload.index("if (!selfTestRequested) _ = RecoverLocalEngineAtStartupAsync();") > onload.index("Browser.CoreWebView2.NavigationCompleted")
generation=s.split("private async Task Generate(",1)[1].split("private void PersistChat(",1)[0]
assert generation.index("await StartLocalEngine(cancellation.Token);") < generation.index('new HttpRequestMessage(HttpMethod.Post, Api + "/api/generate")')
assert generation.index("NOX_MODEL_NOT_REGISTERED:") < generation.index('new HttpRequestMessage(HttpMethod.Post, Api + "/api/generate")')
assert "cancellation.Token.ThrowIfCancellationRequested();" in generation
assert "active?.Cancel();" in s
assert 'ps.Environment["OLLAMA_MODELS"] = modelDir;' in s
print("NOX_TECHFIRST_PROVIDER_SOURCE_ONLY_PASS")
