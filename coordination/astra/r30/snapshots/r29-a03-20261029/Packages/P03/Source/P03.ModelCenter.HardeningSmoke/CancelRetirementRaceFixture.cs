using System.Reflection;
using Nox.P03;

// Authored native fixture, NOT RUN in this source-only environment. Invoke
// await CancelRetirementRaceFixture.RunAsync() from native smoke after review.
// Reflection supplies the retired captured-token state deterministically;
// this is not a real HTTP download or a timing-based Windows acceptance test.
public static class CancelRetirementRaceFixture
{
    public static async Task RunAsync()
    {
        await ScenarioAsync(retired: true);
        await ScenarioAsync(retired: false);
    }

    private static async Task ScenarioAsync(bool retired)
    {
        var root = Path.Combine(Path.GetTempPath(), "NOX_P03_CANCEL_RETIRE_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var store = new ModelDownloadQueueStore(root);
            var source = new Uri("https://ollama.com/library/tinyllama");
            var model = ModelCatalog.Get("tinyllama") with {
                EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
                ExactTag = "tinyllama:fixture", Version = "fixture", License = "fixture-only",
                ArtifactBytes = 100, RequiredDiskBytes = 200, RecommendedRamBytes = 300,
                ExpectedSha256 = new string('a', 64), ExpectedManifestDigestSha256 = new string('b', 64),
                ImmutableRevision = "sha256:" + new string('b', 64), CompatibilityReviewed = true,
                LicenseEvidenceUri = source, CompatibilityEvidenceUri = source
            };
            var job = await store.EnqueueVerifiedPullAsync(model, true);
            if (await store.TryStartQueuedAsync(job.Id) is null) throw new Exception("fixture queue claim failed");
            using var http = new HttpClient(new NoNetwork()) { BaseAddress = new Uri("http://127.0.0.1:11434/") };
            var worker = new ModelDownloadQueueWorker(store, new OllamaModelAdapter(http, root),
                new ModelLifecyclePublisher(new NoEvents()));
            var field = typeof(ModelDownloadQueueWorker).GetField("_running", BindingFlags.NonPublic | BindingFlags.Instance)
                ?? throw new Exception("original worker registration field missing");
            var running = (Dictionary<Guid, CancellationTokenSource>)field.GetValue(worker)!;
            using var token = new CancellationTokenSource();
            using var callback = token.Token.Register(() => {
                // A second thread must be able to enter owner cleanup while
                // Cancel invokes callbacks; holding _running here deadlocks it.
                if (!Task.Run(() => { lock (running) { } }).Wait(TimeSpan.FromSeconds(5)))
                    throw new Exception("worker holds registration lock during cancellation callback");
            });
            lock (running) running[job.Id] = token;
            if (retired) token.Dispose(); // captured reference has retired before signalling
            if (!await worker.CancelAsync(job.Id)) throw new Exception("durable STOP request not accepted");
            if (!retired && !token.IsCancellationRequested) throw new Exception("live token not cancelled");
            var persisted = (await store.ReadAsync()).Single(x => x.Id == job.Id);
            if (persisted.State != ModelJobState.Cancelling)
                throw new Exception("request ACK fabricated a terminal cancellation state");
            lock (running) running.Remove(job.Id);
        }
        finally { Directory.Delete(root, recursive: true); }
    }

    private sealed class NoNetwork : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) =>
            throw new Exception("fixture must not contact Ollama");
    }
    private sealed class NoEvents : IModelLifecycleEventSink
    {
        public ValueTask PublishToP01Async(ModelLifecycleEvent item, CancellationToken ct) => ValueTask.CompletedTask;
        public ValueTask PublishToP05Async(ModelLifecycleEvent item, CancellationToken ct) => ValueTask.CompletedTask;
    }
}
