using NoxP04.Rag;

internal static class Program
{
    private static void Require(bool ok, string code)
    {
        if (!ok) throw new InvalidOperationException(code);
    }

    public static async Task<int> Main()
    {
        // Only synthetic example text. A real installed Ollama embed model is required.
        var model = Environment.GetEnvironmentVariable("NOX_P04_EMBED_MODEL");
        if (string.IsNullOrWhiteSpace(model))
        {
            Console.Error.WriteLine("HOLD_LOCAL_EMBEDDING_MODEL_NOT_CONFIGURED");
            return 3;
        }

        var root = Path.Combine(Path.GetTempPath(), "NOX_P04_LIVE_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        using var deadline = new CancellationTokenSource(TimeSpan.FromMinutes(3));
        try
        {
            var address = Environment.GetEnvironmentVariable("NOX_P04_OLLAMA_LOOPBACK") ?? "http://127.0.0.1:11434/";
            using var rag = new RagService(new Uri(address), model, Path.Combine(root, "index.json"));
            var ingest = new RagIngestionService(rag);
            var contextProvider = new RagChatContextProvider(ingest);
            const string owner = "S-1-5-21-1000";
            const string otherOwner = "S-1-5-21-2000";
            const string conversation = "synthetic-live-check";
            const string source = "synthetic.txt";

            var first = await ingest.IngestTextAsync(owner, conversation, source, "synthetic.txt",
                "An orange moon rises over a quiet sea.", deadline.Token);
            Require(first.IndexedChunks >= 1, "LIVE_INGEST_FAILED");

            var retrieved = await rag.SearchAsync(owner, conversation, "orange moon", cancellationToken: deadline.Token);
            Require(retrieved.Count >= 1 && retrieved[0].SourceId == source, "LIVE_EMBEDDING_SEARCH_FAILED");
            Require(retrieved[0].ChunkSha256.Length == 64, "LIVE_CITATION_HASH_MISSING");

            var chatContext = await contextProvider.RetrieveAsync(owner, conversation, "orange moon",
                cancellationToken: deadline.Token);
            Require(chatContext.ContextText.Contains("SHA256:", StringComparison.Ordinal),
                "LIVE_CHAT_CONTEXT_MISSING_CITATION");
            Require(chatContext.Sources.Count >= 1, "LIVE_CHAT_CONTEXT_SOURCES_MISSING");
            Require((await rag.SearchAsync(otherOwner, conversation, "orange moon",
                cancellationToken: deadline.Token)).Count == 0, "LIVE_OWNER_ACL_FAILED");

            await ingest.IngestTextAsync(owner, conversation, source, "synthetic.txt",
                "A blue river flows beneath distant hills.", deadline.Token);
            var changed = await rag.SearchAsync(owner, conversation, "blue river",
                cancellationToken: deadline.Token);
            Require(changed.Count >= 1 && changed.All(x => !x.Text.Contains("orange moon", StringComparison.Ordinal)),
                "LIVE_UPSERT_OLD_CHUNKS_PRESENT");

            Require(!await rag.DeleteSourceAsync(otherOwner, conversation, source, deadline.Token),
                "LIVE_CROSS_OWNER_DELETE_ALLOWED");
            Require(await rag.DeleteSourceAsync(owner, conversation, source, deadline.Token),
                "LIVE_DELETE_FAILED");
            Require((await rag.SearchAsync(owner, conversation, "blue river",
                cancellationToken: deadline.Token)).Count == 0, "LIVE_DELETE_NOT_PERSISTED");
            Console.WriteLine("P04_REAL_OLLAMA_RAG_SMOKE_PASS: local embedding + citations + ACL + update/delete; NOT_GPU_TRAINING");
            return 0;
        }
        catch (OperationCanceledException)
        {
            Console.Error.WriteLine("HOLD_LOCAL_RAG_TIMEOUT");
            return 3;
        }
        catch (Exception error)
        {
            // Do not print private paths, user data or credentials from the exception.
            Console.Error.WriteLine("HOLD_LOCAL_RAG_" + error.GetType().Name);
            return 3;
        }
        finally
        {
            try { Directory.Delete(root, recursive: true); } catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}
