using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using NoxP04.Rag;
using NoxP04.GpuGuardian;

// In-process contract fixture only: no Ollama model or real embeddings.
// Run as a separate component test; it must never be counted as GPU runtime proof.
internal static class Program
{
    private static int _checks;

    private static void Check(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("P04_RAG_TEST_FAILED: " + name);
        _checks++;
    }

    private static string Sha(string input) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(input))).ToLowerInvariant();

    private static int FreePort()
    {
        var socket = new TcpListener(IPAddress.Loopback, 0);
        socket.Start();
        var port = ((IPEndPoint)socket.LocalEndpoint).Port;
        socket.Stop();
        return port;
    }

    private static async Task ServeAsync(HttpListener listener, CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            HttpListenerContext context;
            try { context = await listener.GetContextAsync().WaitAsync(token); }
            catch (OperationCanceledException) { break; }
            catch (HttpListenerException) when (token.IsCancellationRequested) { break; }
            try
            {
                if (context.Request.HttpMethod != "POST" || context.Request.Url?.AbsolutePath != "/api/embed")
                {
                    context.Response.StatusCode = 404;
                }
                else
                {
                    using var reader = new StreamReader(context.Request.InputStream, Encoding.UTF8);
                    var body = await reader.ReadToEndAsync(token);
                    using var request = JsonDocument.Parse(body);
                    var inputs = request.RootElement.GetProperty("input").EnumerateArray();
                    var embeddings = inputs.Select(e =>
                        e.GetString()?.Contains("alpha", StringComparison.OrdinalIgnoreCase) == true
                            ? new float[] { 1, 0, 0 } : new float[] { 0, 1, 0 }).ToArray();
                    var output = JsonSerializer.SerializeToUtf8Bytes(new { embeddings });
                    context.Response.StatusCode = 200;
                    context.Response.ContentType = "application/json";
                    context.Response.ContentLength64 = output.Length;
                    await context.Response.OutputStream.WriteAsync(output, token);
                }
            }
            catch
            {
                context.Response.StatusCode = 500;
            }
            finally { context.Response.Close(); }
        }
    }

    public static async Task<int> Main()
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        var port = FreePort();
        using var listener = new HttpListener();
        listener.Prefixes.Add("http://127.0.0.1:" + port + "/");
        listener.Start();
        var serving = ServeAsync(listener, stop.Token);
        var directory = Path.Combine(Path.GetTempPath(), "NOX_P04_TEST_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            using var rag = new RagService(new Uri("http://127.0.0.1:" + port + "/"),
                "no-model-test-double", Path.Combine(directory, "index.json"));
            var ingest = new RagIngestionService(rag);
            var eco = GpuModePolicy.For(GpuMode.ECO);
            var balanced = GpuModePolicy.For(GpuMode.BALANCED);
            var intensive = GpuModePolicy.For(GpuMode.INTENSIVE);
            Check(eco.QueueStartDelay > balanced.QueueStartDelay &&
                  balanced.QueueStartDelay > intensive.QueueStartDelay, "gpu scheduling profiles");
            Check(eco.MaximumConcurrentJobs == 1 && balanced.MaximumConcurrentJobs == 1 &&
                  intensive.MaximumConcurrentJobs == 1, "single training queue");
            var missingSensor = new GpuTelemetrySample(DateTimeOffset.UtcNow, "N_D",
                null, null, null, null, null, null, null, "nvidia-smi", "SENSOR_UNAVAILABLE");
            Check(GpuGuardian.ThermalHoldReason(missingSensor, 83) ==
                "GPU_TEMPERATURE_UNAVAILABLE", "gpu sensor missing fail-closed");
            var highTemp = missingSensor with { State = "READY", TemperatureC = 90 };
            Check(GpuGuardian.ThermalHoldReason(highTemp, 83) ==
                "GPU_TEMPERATURE_LIMIT_EXCEEDED", "gpu overheat stop");
            try {
                GpuGuardian.ThermalHoldReason(missingSensor, double.NaN);
                throw new InvalidOperationException("P04_RAG_TEST_FAILED: nonfinite threshold accepted");
            } catch (ArgumentOutOfRangeException) { _checks++; }

            const string ownerA = "S-1-5-21-1100";
            const string ownerB = "S-1-5-21-2200";
            const string conversation = "conversation-a";
            const string source = "source-fixture-a";

            try
            {
                await ingest.IngestTextAsync("S-1-not-a-sid", conversation, "invalid-owner", "fixture.md", "alpha");
                throw new InvalidOperationException("RAG_INVALID_OWNER_ACCEPTED");
            }
            catch (ArgumentException) { _checks++; }
            try
            {
                await ingest.IngestTextAsync(ownerA, new string('c', 257), "invalid-conversation", "fixture.md", "alpha");
                throw new InvalidOperationException("RAG_INVALID_CONVERSATION_ACCEPTED");
            }
            catch (ArgumentException) { _checks++; }
            var stored = await ingest.IngestTextAsync(ownerA, conversation, source, "fixture.md", "alpha original");
            Check(stored.IndexedChunks > 0, "ingest");
            Check(stored.SourceIdentitySha256 == Sha("alpha original"), "source identity");

            var hits = await rag.SearchAsync(ownerA, conversation, "alpha");
            Check(hits.Count > 0 && hits[0].Text.Contains("alpha original"), "authorized search");
            Check(hits[0].ChunkSha256 == Sha(hits[0].Text), "citation hash");
            Check(RagService.BuildContext(hits).Contains("SHA256:"), "citation context");
            // A full SHA citation must not be attached to a truncated chunk.
            // If the first hit is too large, preserve a later valid small hit.
            var hugeText = new string('Z', 600);
            var smallText = "small verified passage";
            var huge = new RagSearchResult(ownerA, conversation, "too-big",
                "huge.md", Sha(hugeText), Sha(hugeText), 0, 0.9, hugeText);
            var smallCitation = new RagSearchResult(ownerA, conversation, "fits",
                "small.md", Sha(smallText), Sha(smallText), 0, 0.8, smallText);
            var boundedContext = RagService.BuildContext(
                new[] { huge, smallCitation }, 256);
            Check(!boundedContext.Contains("huge.md") &&
                  boundedContext.Contains(smallText) &&
                  boundedContext.Contains("SHA256:" + Sha(smallText)),
                "bounded context retains only complete SHA-verified passages");
            // Public formatter must fail closed if the caller supplies a forged
            // chunk identity, even if its shape and citation syntax look valid.
            try
            {
                var tamperedCitation = smallCitation with { ChunkSha256 = Sha("wrong bytes") };
                RagService.BuildContext(new[] { tamperedCitation }, 256);
                throw new InvalidOperationException("RAG_FORGED_CITATION_ACCEPTED");
            }
            catch (InvalidDataException) { _checks++; }
            try
            {
                var foreignOwner = smallCitation with { OwnerSid = ownerB };
                RagService.BuildContext(new[] { smallCitation, foreignOwner }, 512);
                throw new InvalidOperationException("RAG_MIXED_OWNER_CITATION_ACCEPTED");
            }
            catch (InvalidDataException) { _checks++; }
            try
            {
                var foreignChat = smallCitation with { ConversationId = "other-conversation" };
                RagService.BuildContext(new[] { smallCitation, foreignChat }, 512);
                throw new InvalidOperationException("RAG_MIXED_CHAT_CITATION_ACCEPTED");
            }
            catch (InvalidDataException) { _checks++; }
            using (var reopened = new RagService(new Uri("http://127.0.0.1:" + port + "/"),
                "no-model-test-double", Path.Combine(directory, "index.json")))
            {
                var persisted = await reopened.SearchAsync(ownerA, conversation, "alpha");
                Check(persisted.Count > 0 && persisted[0].ChunkSha256 == hits[0].ChunkSha256,
                    "index persists across RAG service restart");
                Check((await reopened.SearchAsync(ownerB, conversation, "alpha")).Count == 0,
                    "persisted index still enforces owner ACL");
            }
            await ingest.IngestTextAsync(ownerA, conversation, "citation-safety", "source]#note.md", "alpha citation");
            var safelyEncoded = await ingest.BuildContextAsync(ownerA, conversation, "alpha");
            Check(safelyEncoded.ContextText.Contains("source%5D%23note.md"), "citation filename percent-encoded");
            Check(!safelyEncoded.ContextText.Contains("source]#note.md"), "unescaped filename absent");
            Check(await rag.DeleteSourceAsync(ownerA, conversation, "citation-safety"), "citation fixture cleanup");

            Check((await rag.SearchAsync(ownerB, conversation, "alpha")).Count == 0, "owner isolation");
            Check((await rag.SearchAsync(ownerA, "other-conversation", "alpha")).Count == 0, "conversation isolation");

            await ingest.IngestTextAsync(ownerA, conversation, source, "fixture.md", "beta updated");
            var updated = await rag.SearchAsync(ownerA, conversation, "beta");
            Check(updated.Count > 0 && updated.All(h => h.Text.Contains("beta updated")), "source upsert replaces old chunks");
            Check(updated.All(h => !h.Text.Contains("alpha original")), "old revision removed");

            Check(!await rag.DeleteSourceAsync(ownerB, conversation, source), "wrong-owner deletion denied");
            Check(await rag.DeleteSourceAsync(ownerA, conversation, source), "source delete");
            Check((await rag.SearchAsync(ownerA, conversation, "beta")).Count == 0, "deleted source cannot be retrieved");

            await ingest.IngestTextAsync(ownerA, conversation, "s1", "a.txt", "alpha content");
            await ingest.IngestTextAsync(ownerA, conversation, "s2", "b.txt", "beta content");
            Check(await rag.DeleteConversationAsync(ownerA, conversation) == 2, "conversation delete");
            Check((await rag.SearchAsync(ownerA, conversation, "alpha")).Count == 0, "deleted conversation empty");
            using (var reopened = new RagService(new Uri("http://127.0.0.1:" + port + "/"),
                "no-model-test-double", Path.Combine(directory, "index.json")))
            {
                Check((await reopened.SearchAsync(ownerA, conversation, "alpha")).Count == 0,
                    "deleted conversation stays deleted across service restart");
            }
            var indexPath = Path.Combine(directory, "index.json");
            using (var oversized = new FileStream(indexPath, FileMode.Create, FileAccess.Write, FileShare.None))
                oversized.SetLength(256L * 1024 * 1024 + 1);
            try
            {
                await rag.SearchAsync(ownerA, conversation, "alpha");
                throw new InvalidOperationException("RAG_OVERSIZE_INDEX_ACCEPTED");
            }
            catch (InvalidDataException) { _checks++; }
            Console.WriteLine("P04_RAG_SYNTHETIC_COMPONENT_PASS: " + _checks + " checks; NO_REAL_OLLAMA_OR_GPU");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("P04_RAG_SYNTHETIC_COMPONENT_FAIL: " + ex.GetType().Name + ": " + ex.Message);
            return 1;
        }
        finally
        {
            stop.Cancel();
            listener.Stop();
            try { await serving; } catch (OperationCanceledException) { }
            try { Directory.Delete(directory, recursive: true); } catch { }
        }
    }
}
