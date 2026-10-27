using System.Net;
using System.Text;
using Nox.P03;

// No external NuGet test framework; deterministic local-only source contract smoke.
var root = Path.Combine(Path.GetTempPath(), "NOX_P03_SMOKE_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try
{
    var store = new ModelDownloadQueueStore(root);
    await AssertThrowsAsync<InvalidOperationException>(() => store.EnqueueAsync(
        ModelJobKind.GgufImport, "local:test", "fake.gguf", true,
        "https://ollama.com/library/tinyllama"));
    await AssertThrowsAsync<InvalidDataException>(() => store.EnqueueVerifiedGgufAsync(
        "local:test", "fake.gguf", 123, "not-a-hash", "receipt",
        "https://ollama.com/library/tinyllama"));
    await AssertThrowsAsync<InvalidOperationException>(() =>
        store.EnqueueVerifiedPullAsync(ModelCatalog.Get("tinyllama"), true));
    var reviewedFixture = ModelCatalog.Get("tinyllama") with
    {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:1.1b", Version = "test-version", License = "test-license",
        ArtifactBytes = 128, RequiredDiskBytes = 256, RecommendedRamBytes = 512,
        ExpectedSha256 = new string('b', 64),
        ExpectedManifestDigestSha256 = new string('a', 64),
        ImmutableRevision = "test-immutable-revision", CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri("https://ollama.com/library/tinyllama"),
        CompatibilityEvidenceUri = new Uri("https://ollama.com/library/tinyllama")
    };
    var reviewed = await store.EnqueueVerifiedPullAsync(reviewedFixture, true);
    if (reviewed.ExpectedOllamaDigest != new string('a', 64))
        throw new Exception("Manifest pin was not persisted");
    await AssertThrowsAsync<InvalidOperationException>(() => store.EnqueueAsync(
        ModelJobKind.OllamaPull, "tinyllama:1.1b", null, true, "https://ollama.com/library/tinyllama"));
    var queued = reviewed;
    if ((await store.ReadAsync()).Count != 1) throw new Exception("Verified queue persist failed");
    await AssertThrowsAsync<InvalidOperationException>(() => store.UpdateAsync(queued.Id,
        j => j with { ExpectedOllamaDigest = new string('c',64) }));
    await store.UpdateAsync(queued.Id, j => j with { State = ModelJobState.Running });
    var recovered = await store.RecoverInterruptedAsync();
    if (recovered != 1) throw new Exception("Interrupted queue not recovered");
    var retry = await store.RetryAsync(queued.Id);
    if (retry is null || retry.Id == queued.Id || retry.State != ModelJobState.Queued)
        throw new Exception("Retry failed");
    await File.WriteAllTextAsync(Path.Combine(root, "p03-model-download-queue.json"), "{broken");
    await AssertThrowsAsync<InvalidDataException>(async () => { await store.ReadAsync(); });
    if ((await File.ReadAllTextAsync(Path.Combine(root, "p03-model-download-queue.json"))) != "{broken")
        throw new Exception("Corrupt queue overwritten");

    // Restore a byte-verified backup after deliberate corruption, no silent overwrite.
    await AssertThrowsAsync<InvalidOperationException>(() => store.RestoreBackupAsync(false));
    await store.RestoreBackupAsync(true);
    if ((await store.ReadAsync()).Count == 0) throw new Exception("Backup restore failed");
    if (!ModelCatalog.IsValidFamilyIndex()) throw new Exception("Family discovery index mutated");
    var validCommand = System.Text.Json.JsonSerializer.Serialize(new {
        type = "p03.command.v1", action = "pull", commandId = "test-1",
        modelId = "tinyllama", licenseAcknowledged = true });
    if (Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(validCommand,
        await store.ReadAsync(), new[] { reviewedFixture }, new(), out _))
        throw new Exception("Unauthorized pull command accepted");
    if (!Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(validCommand,
        await store.ReadAsync(), new[] { reviewedFixture }, new(Pull: true), out var parsed)
        || parsed?.Action != "pull") throw new Exception("Authorized pull command rejected");
    var fakeManifest = new string('a', 64);
    var job = queued with { State = ModelJobState.Running,
        ExpectedOllamaDigest = fakeManifest, ImmutableRevision = "verified-fixture-revision" };
    await AssertThrowsAsync<InvalidDataException>(() => oklessPull());
    async Task oklessPull()
    {
        using var unpinnedClient = new HttpClient(new FakeOllamaHandler(true)) { BaseAddress = new Uri("http://localhost:11434/") };
        await new OllamaModelAdapter(unpinnedClient, Path.Combine(root, "receipts"))
            .PullAsync(queued with { ExpectedOllamaDigest = null, ImmutableRevision = null }, (e, token) => ValueTask.CompletedTask, default);
    }
    var url = "http://localhost:11434/";
    using var okClient = new HttpClient(new FakeOllamaHandler(true)) { BaseAddress = new Uri(url) };
    var okAdapter = new OllamaModelAdapter(okClient, Path.Combine(root, "receipts"));
    var result = await okAdapter.PullAsync(job, (e, token) => ValueTask.CompletedTask, default);
    if (result != "sha256:" + fakeManifest) throw new Exception("Expected local model digest");
    using var badClient = new HttpClient(new FakeOllamaHandler(false)) { BaseAddress = new Uri(url) };
    var badAdapter = new OllamaModelAdapter(badClient, Path.Combine(root, "receipts"));
    await AssertThrowsAsync<InvalidDataException>(() => badAdapter.PullAsync(job,
        (e, token) => ValueTask.CompletedTask, default));
    using var mismatchedClient = new HttpClient(new FakeOllamaHandler(true)) { BaseAddress = new Uri(url) };
    await AssertThrowsAsync<InvalidDataException>(() => new OllamaModelAdapter(mismatchedClient,
        Path.Combine(root, "receipts")).PullAsync(job with { ExpectedOllamaDigest = new string('b', 64) },
        (e, token) => ValueTask.CompletedTask, default));
    // Real local file-byte verification against a deterministic fake Ollama API.
    var smallGguf = Path.Combine(root, "fixture.gguf");
    await File.WriteAllBytesAsync(smallGguf, Encoding.ASCII.GetBytes("GGUFsmall-fixture"));
    var smallBytes = new FileInfo(smallGguf).Length;
    var ggufSha = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(smallGguf))).ToLowerInvariant();
    var importJob = await store.EnqueueVerifiedGgufAsync("local:fixture", smallGguf,
        smallBytes, ggufSha, "rights-test-fixture", "https://ollama.com/library/tinyllama");
    using var importClient = new HttpClient(new FakeOllamaHandler(true)) { BaseAddress = new Uri(url) };
    var importAdapter = new OllamaModelAdapter(importClient, Path.Combine(root, "receipts"));
    var imported = await importAdapter.ImportGgufAsync(importJob,
        (e, token) => ValueTask.CompletedTask, default);
    if (imported.Bytes != smallBytes || imported.Sha256 != ggufSha ||
        !File.Exists(importAdapter.ReceiptPathFor(importJob.Id))) throw new Exception("GGUF import receipt failed");
    Console.WriteLine("P03_SMOKE_PASS: queue/provenance/restore/bridge/Pull/GGUF digest");
}
finally { Directory.Delete(root, recursive: true); }

static async Task AssertThrowsAsync<T>(Func<Task> f) where T : Exception
{
    try { await f(); }
    catch (T) { return; }
    throw new Exception("Expected exception: " + typeof(T).Name);
}

sealed class FakeOllamaHandler(bool success) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
    {
        var route = request.RequestUri!.AbsolutePath;
        var response = route switch
        {
            "/api/pull" => new HttpResponseMessage(HttpStatusCode.OK) {
                Content = new StringContent(success
                    ? "{\"status\":\"downloading\",\"digest\":\"sha256:a\",\"completed\":3,\"total\":3}\n{\"status\":\"success\"}\n"
                    : "{\"status\":\"downloading\"}\n", Encoding.UTF8) },
            "/api/create" => new HttpResponseMessage(HttpStatusCode.OK) {
                Content = new StringContent("{\"status\":\"parsing GGUF\"}\n{\"status\":\"success\"}\n", Encoding.UTF8) },
            "/api/tags" => new HttpResponseMessage(HttpStatusCode.OK) {
                Content = new StringContent("{\"models\":[{\"name\":\"tinyllama:1.1b\",\"digest\":\"sha256:" + new string('a',64) + "\"},{\"name\":\"local:fixture\",\"digest\":\"sha256:" + new string('a',64) + "\"}]}" ) },
            _ when route.StartsWith("/api/blobs/sha256:", StringComparison.Ordinal) => new HttpResponseMessage(HttpStatusCode.OK),
            _ => new HttpResponseMessage(HttpStatusCode.NotFound)
        };
        return Task.FromResult(response);
    }
}