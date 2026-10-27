using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using NoxP04.Rag;

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
            const string ownerA = "S-1-5-21-1100";
            const string ownerB = "S-1-5-21-2200";
            const string conversation = "conversation-a";
            const string source = "source-fixture-a";

            var stored = await ingest.IngestTextAsync(ownerA, conversation, source, "fixture.md", "alpha original");
            Check(stored.IndexedChunks > 0, "ingest");
            Check(stored.SourceIdentitySha256 == Sha("alpha original"), "source identity");

            var hits = await rag.SearchAsync(ownerA, conversation, "alpha");
            Check(hits.Count > 0 && hits[0].Text.Contains("alpha original"), "authorized search");
            Check(hits[0].ChunkSha256 == Sha(hits[0].Text), "citation hash");
            Check(RagService.BuildContext(hits).Contains("SHA256:"), "citation context");

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
