using System.Text;
using System.Text.Json;
using Nox.P03;

int pass = 0;
void Assert(bool value, string name) { if (!value) throw new Exception("FAIL " + name); Console.WriteLine("PASS " + name); pass++; }
void MustReject(Action fn, string name) {
    try { fn(); }
    catch (InvalidDataException) { Console.WriteLine("PASS " + name); pass++; return; }
    throw new Exception("FAIL " + name);
}
using var correct = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"sha256:" + new string('a',64) + "\"}]}");
Assert(ModelLocalAttestation.ParseUnambiguousModelDigest(correct.RootElement, "m:1") == "sha256:" + new string('a',64), "T01 pinned local digest");
Assert(ModelLocalAttestation.ParseUnambiguousModelDigest(correct.RootElement, "missing:1") is null, "T02 absent tag stays unknown");
using var duplicated = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"sha256:" + new string('a',64) + "\"},{\"name\":\"m:1\",\"digest\":\"sha256:" + new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(duplicated.RootElement,"m:1"), "T03 duplicate tag denied");
using var invalidSchema = JsonDocument.Parse("{\"models\":{}}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(invalidSchema.RootElement,"m:1"), "T04 nonarray tags denied");
using var invalidDigest = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"sha256:broken\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(invalidDigest.RootElement,"m:1"), "T05 malformed digest denied");
using var missingName = JsonDocument.Parse("{\"models\":[{\"digest\":\"sha256:" + new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(missingName.RootElement,"m:1"), "T06 malformed record denied");
var root = Path.Combine(Path.GetTempPath(),"NOX_P03_HARDEN_"+Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try {
  var file = Path.Combine(root,"valid.gguf"); await File.WriteAllTextAsync(file,"GGUFtest");
  ModelLocalAttestation.RequireRegularUnlinkedFile(file); Assert(true,"T07 regular GGUF allowed");
  var link = Path.Combine(root,"link.gguf");
  try {
    File.CreateSymbolicLink(link, file);
    MustReject(() => ModelLocalAttestation.RequireRegularUnlinkedFile(link),"T08 symlink GGUF denied");
  } catch (UnauthorizedAccessException) { Console.WriteLine("SKIP T08 Windows symlink privilege unavailable"); }
  var receipt = new ModelInstallReceipt("NOX_P03_INSTALL_RECEIPT_V1",Guid.NewGuid(),"m:1","ollama-pull",
      DateTimeOffset.UtcNow,null,null,"sha256:"+new string('a',64),"https://ollama.com/library/m","http://localhost:11434/");
  var receiptFile = Path.Combine(root,"receipt.json");
  await File.WriteAllTextAsync(receiptFile,JsonSerializer.Serialize(receipt,new JsonSerializerOptions(JsonSerializerDefaults.Web)));
  await ModelLocalAttestation.VerifyReceiptAsync(receiptFile, receipt, default);
  Assert(true,"T09 install receipt readback");
  try { await ModelLocalAttestation.VerifyReceiptAsync(receiptFile,receipt with { ModelTag="attacker:tag" },default); throw new Exception("FAIL T10"); }
  catch (InvalidDataException) { Assert(true,"T10 receipt mismatch denied"); }
} finally { Directory.Delete(root,recursive:true); }
Console.WriteLine($"P03_HARDENING_SMOKE_PASS {pass} verified assertions");

// TURBO13 protocol and immutable receipt tests; each uses actual source methods.
int turbo13Pass = 0;
void T13(bool ok, string label) { if (!ok) throw new Exception("FAIL " + label); turbo13Pass++; Console.WriteLine("PASS " + label); }
async Task RejectAsync(Func<Task> test, string label)
{
    try { await test(); }
    catch (InvalidDataException) { T13(true, label); return; }
    throw new Exception("FAIL " + label);
}
async Task Drain(string input)
{
    using var reader = new StringReader(input);
    await foreach (var _ in ModelLocalAttestation.ReadValidatedStreamAsync(reader)) { }
}
// 01. Two valid records across buffer boundaries and CRLF preserve exact fields.
var goodLine = "{\"status\":\"downloading\",\"digest\":\"sha256:" + new string('a',64) + "\",\"completed\":1,\"total\":2}";
using (var reader = new StringReader(goodLine + "\r\n{\"status\":\"success\"}"))
{
    var updates = new List<OllamaStreamUpdate>();
    await foreach (var evt in ModelLocalAttestation.ReadValidatedStreamAsync(reader)) updates.Add(evt);
    T13(updates.Count == 2 && updates[0].Completed == 1 && updates[1].Status == "success", "T13-01 bounded valid CRLF stream");
}
// 02. Oversized first line without a terminator fails before unbounded allocation.
await RejectAsync(() => Drain(new string('x', ModelLocalAttestation.MaxEventCharacters + 1)),
    "T13-02 oversized no-newline line denied");
// 03. Numeric status must be rejected, not reported as a completed download.
await RejectAsync(() => Drain("{\"status\":17}\n"), "T13-03 typed status enforced");
// 04. Negative byte progress is invalid.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"completed\":-1,\"total\":1}\n"),
    "T13-04 negative progress denied");
// 05. Completed bytes must not exceed the total.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"completed\":5,\"total\":2}\n"),
    "T13-05 impossible progress denied");
// 06. A progress layer's digest must be a complete SHA-256.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"digest\":\"sha256:xyz\"}\n"),
    "T13-06 fake layer digest denied");
// 07. Error must be text, not a nested object that bypasses the error branch.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"error\":{}}\n"),
    "T13-07 nonstring error denied");
// 08. A forged second success or arbitrary event after success is rejected.
await RejectAsync(() => Drain("{\"status\":\"success\"}\n{\"status\":\"success\"}\n"),
    "T13-08 duplicate terminal success denied");
// 09. Full timestamp on persisted installation evidence is immutable.
var attestationRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_T13_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(attestationRoot);
try
{
    var r = new ModelInstallReceipt("NOX_P03_INSTALL_RECEIPT_V1", Guid.NewGuid(), "m:1", "gguf-import",
        DateTimeOffset.UtcNow, 8, new string('a',64), "sha256:"+new string('b',64),
        "https://ollama.com/library/m", "http://localhost:11434/");
    await ModelLocalAttestation.WriteNewReceiptAsync(attestationRoot, r, default);
    await RejectAsync(() => ModelLocalAttestation.VerifyReceiptAsync(
        Path.Combine(attestationRoot, r.JobId.ToString("N")+".json"),
        r with { CompletedAtUtc = r.CompletedAtUtc.AddMinutes(1) }, default),
        "T13-09 receipt timestamp mutation denied");
    // 10. A later concurrent operation cannot silently replace an earlier receipt.
    bool duplicateBlocked = false;
    try { await ModelLocalAttestation.WriteNewReceiptAsync(attestationRoot, r, default); }
    catch (IOException) { duplicateBlocked = true; }
    await ModelLocalAttestation.VerifyReceiptAsync(Path.Combine(attestationRoot, r.JobId.ToString("N")+".json"), r, default);
    T13(duplicateBlocked, "T13-10 immutable receipt no overwrite");
}
finally { Directory.Delete(attestationRoot, recursive:true); }
Console.WriteLine($"P03_TURBO13_SMOKE_PASS {turbo13Pass}/10 targeted assertions");

 // E03 final: multiple NOX windows share one persisted queue; no lost updates.
var multiRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_MULTI_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(multiRoot);
try
{
    var a = new ModelDownloadQueueStore(multiRoot);
    var b = new ModelDownloadQueueStore(multiRoot);
    var evidence = "https://ollama.com/library/tinyllama";
    var digestA = new string('a', 64);
    var digestB = new string('b', 64);
    var model = ModelCatalog.Get("tinyllama") with {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:1.1b", Version = "synthetic-fixture", License = "fixture-license",
        ArtifactBytes = 100, RequiredDiskBytes = 200, RecommendedRamBytes = 300,
        ExpectedSha256 = digestB, ExpectedManifestDigestSha256 = digestA,
        ImmutableRevision = "sha256:" + digestA, CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri(evidence), CompatibilityEvidenceUri = new Uri(evidence)
    };
    var sameJobs = await Task.WhenAll(Enumerable.Range(0, 20).Select(i =>
        (i % 2 == 0 ? a : b).EnqueueVerifiedPullAsync(model, true)));
    Assert(sameJobs.Select(j => j.Id).Distinct().Count() == 1,
        "F01 multiple instances deduplicate immutable Pull");
    Assert((await new ModelDownloadQueueStore(multiRoot).ReadAsync()).Count == 1,
        "F02 queue stays durable across independent instances");
    var file = Path.Combine(multiRoot, "sample.gguf");
    await File.WriteAllBytesAsync(file, Encoding.ASCII.GetBytes("GGUFsynthetic-byteproof"));
    var sha = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(file))).ToLowerInvariant();
    var size = new FileInfo(file).Length;
    await Task.WhenAll(Enumerable.Range(0, 10).Select(i =>
        (i % 2 == 0 ? a : b).EnqueueVerifiedGgufAsync("local:example" + i,
            file, size, sha, "synthetic-rights", evidence)));
    Assert((await new ModelDownloadQueueStore(multiRoot).ReadAsync()).Count == 11,
        "F03 concurrent separate GGUF requests cannot overwrite each other");
    var started = await a.UpdateAsync(sameJobs[0].Id, j => j with { State = ModelJobState.Running });
    Assert(started?.State == ModelJobState.Running, "F04 state persisted under queue lease");
    var restarted = new ModelDownloadQueueStore(multiRoot);
    Assert(await restarted.RecoverInterruptedAsync() == 1, "F05 interrupted job recovered");
    var retried = await Task.WhenAll(a.RetryAsync(sameJobs[0].Id), b.RetryAsync(sameJobs[0].Id));
    Assert(retried.All(x => x is not null) &&
           retried.Select(x => x!.Id).Distinct().Count() == 1,
        "F06 two concurrent retries share one child job");
    Assert((await restarted.ReadAsync()).Count == 12,
        "F07 all prior jobs retained after retry");
}
finally { Directory.Delete(multiRoot, recursive: true); }
Console.WriteLine("P03_FINAL_QUEUE_CONCURRENCY_PASS 7/7");


 // One existing-host HTTP client; no system proxy, external redirects, or alternate host.
using (var safeClient = OllamaLoopbackHttpClientFactory.Create(new Uri("http://localhost:11434/")))
    Assert(safeClient.BaseAddress!.Host == "127.0.0.1",
        "F08 one shared loopback transport canonicalizes localhost");
foreach (var bad in new[] {
    "http://example.com:11434/", "https://localhost:11434/",
    "http://user:secret@localhost:11434/", "http://localhost:11434/api/",
    "http://localhost:11434/?redirect=1" })
{
    try {
        OllamaLoopbackHttpClientFactory.ValidateAndCanonicalize(new Uri(bad));
        throw new Exception("FAIL F09 disallowed host/URL " + bad);
    }
    catch (InvalidOperationException) { /* expected */ }
}
Assert(true, "F09 all remote/proxy-ambiguous endpoint shapes denied");
Console.WriteLine("P03_FINAL_TRANSPORT_POLICY_PASS 2/2");

 // Owner3 atomic-claim regression: only one process starts a given model job.
var atomicRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_CLAIM_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(atomicRoot);
try
{
    var left = new ModelDownloadQueueStore(atomicRoot);
    var right = new ModelDownloadQueueStore(atomicRoot);
    var approved = ModelCatalog.Get("tinyllama") with {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:1.1b", Version = "synthetic-only", License = "synthetic-license",
        ArtifactBytes = 100, RequiredDiskBytes = 200, RecommendedRamBytes = 300,
        ExpectedSha256 = new string('b', 64), ExpectedManifestDigestSha256 = new string('a', 64),
        ImmutableRevision = "sha256:" + new string('a', 64), CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri("https://ollama.com/library/tinyllama"),
        CompatibilityEvidenceUri = new Uri("https://ollama.com/library/tinyllama")
    };
    var ticket = await left.EnqueueVerifiedPullAsync(approved, true);
    var claims = await Task.WhenAll(Enumerable.Range(0, 24).Select(i =>
        (i % 2 == 0 ? left : right).TryStartQueuedAsync(ticket.Id)));
    Assert(claims.Count(x => x is not null) == 1, "F10 only one process acquires model job");
    var persistedClaim = (await right.ReadAsync()).Single();
    Assert(persistedClaim.State == ModelJobState.Running && persistedClaim.Attempts == 1,
        "F11 exactly one attempt persisted");
    var toCancel = await right.EnqueueVerifiedPullAsync(approved with {
        ExactTag = "tinyllama:test-cancel", ImmutableRevision = "sha256:" + new string('b', 64),
        ExpectedManifestDigestSha256 = new string('b', 64) }, true);
    Assert(await right.CancelQueuedAsync(toCancel.Id), "F12 queue STOP persisted");
    Assert(await left.TryStartQueuedAsync(toCancel.Id) is null,
        "F13 cancelled queued job can never be claimed");
    Assert(await right.RequestCancelAsync(ticket.Id), "F14 remote STOP accepted");
    Assert((await left.ReadAsync()).Single(j => j.Id == ticket.Id).State ==
        ModelJobState.Cancelling, "F15 stop state visible to another NOX window");
    Assert(await left.RequestCancelAsync(ticket.Id), "F16 second STOP is idempotent");
    Assert(await right.TryStartQueuedAsync(ticket.Id) is null,
        "F17 remote STOP cannot restart an active job");
}
finally { Directory.Delete(atomicRoot, recursive: true); }
Console.WriteLine("P03_ATOMIC_CLAIM_TEST_PASS 4/4");

 // F18-F21: the ACTUAL worker must observe a STOP from another NOX window.
 // No real model or network request is made; the fake Pull stream waits for
 // cancellation, so only an actual worker STOP can complete this scenario.
var stopRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_STOP_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(stopRoot);
try
{
    var sourceQueue = new ModelDownloadQueueStore(stopRoot);
    var remoteQueue = new ModelDownloadQueueStore(stopRoot);
    var reviewed = ModelCatalog.Get("tinyllama") with {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:worker-stop", Version = "synthetic-fixture",
        License = "synthetic-license", ArtifactBytes = 100,
        RequiredDiskBytes = 200, RecommendedRamBytes = 300,
        ExpectedSha256 = new string('b', 64),
        ExpectedManifestDigestSha256 = new string('a', 64),
        ImmutableRevision = "sha256:" + new string('a', 64),
        CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri("https://ollama.com/library/tinyllama"),
        CompatibilityEvidenceUri = new Uri("https://ollama.com/library/tinyllama")
    };
    var waitingJob = await sourceQueue.EnqueueVerifiedPullAsync(reviewed, true);
    using var loopback = new HttpClient(new StalledOllamaHandler()) {
        BaseAddress = new Uri("http://127.0.0.1:11434/")
    };
    var adapter = new OllamaModelAdapter(loopback, stopRoot);
    var publisher = new ModelLifecyclePublisher(new SilentP03Sink());
    var owningWorker = new ModelDownloadQueueWorker(sourceQueue, adapter, publisher);
    var secondWindow = new ModelDownloadQueueWorker(remoteQueue, adapter, publisher);
    var operation = owningWorker.RunNextAsync();
    var observedStart = false;
    for (var i = 0; i < 150; i++)
    {
        var saved = (await remoteQueue.ReadAsync()).Single();
        if (saved.State == ModelJobState.Running)
        {
            observedStart = true;
            break;
        }
        await Task.Delay(20);
    }
    Assert(observedStart, "F18 actual worker claimed job before cross-window STOP");
    Assert(await remoteQueue.RecoverInterruptedAsync() == 0,
        "F22 second NOX window cannot recover a live working job");
    Assert((await remoteQueue.ReadAsync()).Single().State == ModelJobState.Running,
        "F23 active worker state survives another window startup");
    var remoteStopAccepted = await secondWindow.CancelAsync(waitingJob.Id);
    var stopSnapshot = (await remoteQueue.ReadAsync()).Single();
    Assert(remoteStopAccepted,
        "F19 second-window STOP accepted; state=" + stopSnapshot.State +
        " error=" + stopSnapshot.Error);
    await operation.WaitAsync(TimeSpan.FromSeconds(8));
    var finished = (await remoteQueue.ReadAsync()).Single();
    Assert(finished.State == ModelJobState.Cancelled,
        "F20 worker cancelled stalled stream through shared STOP");
    Assert(!File.Exists(adapter.ReceiptPathFor(waitingJob.Id)),
        "F21 canceled job cannot forge an installed-model receipt");
}
finally { Directory.Delete(stopRoot, recursive: true); }
Console.WriteLine("P03_SHARED_WORKER_STOP_PASS 4/4");

sealed class SilentP03Sink : IModelLifecycleEventSink
{
    public ValueTask PublishToP01Async(ModelLifecycleEvent evt, CancellationToken ct) => ValueTask.CompletedTask;
    public ValueTask PublishToP05Async(ModelLifecycleEvent evt, CancellationToken ct) => ValueTask.CompletedTask;
}

sealed class StalledOllamaHandler : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        if (request.RequestUri?.AbsolutePath != "/api/pull")
            throw new InvalidOperationException("Only synthetic Ollama Pull is available");
        return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK) {
            Content = new StreamContent(new StalledP03Stream())
        });
    }
}

sealed class StalledP03Stream : Stream
{
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
    public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override Task<int> ReadAsync(byte[] buffer, int offset, int count,
        CancellationToken ct) => ReadAsync(buffer.AsMemory(offset, count), ct).AsTask();
    public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
    {
        await Task.Delay(Timeout.Infinite, ct);
        return 0;
    }
    public override void Flush() => throw new NotSupportedException();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long length) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}
