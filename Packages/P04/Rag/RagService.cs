using System.Net;
using System.Net.Http.Json;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace NoxP04.Rag;

/// <summary>
/// Text prepared by the host after its file picker, ACL, and safe text-extraction
/// steps. SourceIdentitySha256 must identify the original source file.
/// </summary>
public sealed record RagSourceDocument(
    string OwnerSid,
    string ConversationId,
    string SourceId,
    string FileName,
    string SourceIdentitySha256,
    string Text);

/// <summary>A retrieved chunk with enough provenance for a user-visible citation.</summary>
public sealed record RagSearchResult(
    string OwnerSid,
    string ConversationId,
    string SourceId,
    string FileName,
    string SourceIdentitySha256,
    string ChunkSha256,
    int ChunkIndex,
    double Score,
    string Text);

/// <summary>
/// Local Ollama-backed retrieval. This class accepts already-extracted text;
/// the host must authenticate the Windows SID and authorize the source before ingest.
/// Embeddings are always obtained from a no-proxy, no-redirect loopback endpoint;
/// no fallback or synthetic vectors are generated.
/// </summary>
public sealed class RagService : IDisposable
{
    private const string IndexSchema = "NOX-RAG-INDEX-v1";
    private const int ChunkCharacters = 1200;
    private const int ChunkOverlap = 120;
    private const int EmbeddingBatchSize = 32;
    private const int MaximumEmbeddingDimensions = 16_384;
    private const int MaximumInputCharacters = 2_000_000;
    private const long MaximumIndexFileBytes = 256L * 1024 * 1024;
    private static readonly TimeSpan EmbeddingRequestTimeout = TimeSpan.FromMinutes(2);
    private const int MaximumResults = 20;
    private const int MaximumSourceIdCharacters = 256;
    private readonly SemaphoreSlim _processGate = new(1, 1);
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly HttpClient _http;
    private readonly Uri _embedEndpoint;
    private readonly string _model;
    private readonly string _indexPath;
    private bool _disposed;

    public RagService(Uri ollamaBaseUri, string embeddingModel, string? indexPath = null)
    {
        ArgumentNullException.ThrowIfNull(ollamaBaseUri);
        ArgumentException.ThrowIfNullOrWhiteSpace(embeddingModel);
        if (!IsLoopbackHttp(ollamaBaseUri) || !string.IsNullOrEmpty(ollamaBaseUri.UserInfo) ||
            !string.IsNullOrEmpty(ollamaBaseUri.Query) || !string.IsNullOrEmpty(ollamaBaseUri.Fragment) ||
            !string.Equals(ollamaBaseUri.AbsolutePath, "/", StringComparison.Ordinal))
            throw new ArgumentException("RAG accepts only a plain loopback Ollama base URI without credentials, path, query, or fragment.", nameof(ollamaBaseUri));

        var normalizedModel = embeddingModel.Trim();
        if (normalizedModel.Length > 128 || normalizedModel.Any(char.IsControl))
            throw new ArgumentException("Embedding model name must be at most 128 printable characters.", nameof(embeddingModel));
        _model = normalizedModel;
        _embedEndpoint = new UriBuilder(ollamaBaseUri) { Path = "/api/embed", Query = string.Empty, Fragment = string.Empty }.Uri;
        _http = new HttpClient(new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseProxy = false,
            ConnectTimeout = TimeSpan.FromSeconds(5)
        }) { Timeout = Timeout.InfiniteTimeSpan };
        _indexPath = ResolveIndexPath(indexPath);
    }

    /// <summary>
    /// Embeds and atomically replaces one source's chunks. Callers must enforce
    /// authorization before passing the source text to this service.
    /// </summary>
    public async Task<int> IngestTextAsync(RagSourceDocument source, CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ValidateSource(source);
        if (source.Text.Length > MaximumInputCharacters)
            throw new ArgumentException("RAG source exceeds the supported text limit.", nameof(source));

        var chunks = SplitIntoChunks(source.Text);
        if (chunks.Count == 0) throw new ArgumentException("RAG source contains no searchable text.", nameof(source));
        var vectors = await EmbedBatchesAsync(chunks, cancellationToken).ConfigureAwait(false);
        var storedChunks = new List<ChunkDocument>(chunks.Count);
        for (var i = 0; i < chunks.Count; i++)
        {
            storedChunks.Add(new ChunkDocument
            {
                ChunkIndex = i,
                ChunkSha256 = Sha256(chunks[i]),
                Text = chunks[i],
                Vector = vectors[i]
            });
        }

        await _processGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            using var indexLock = await AcquireIndexLockAsync(cancellationToken).ConfigureAwait(false);
            var current = LoadIndex();
            EnsureCompatible(current, vectors[0].Length);
            var next = CloneIndex(current);
            next.Model = _model;
            next.VectorDimensions = vectors[0].Length;
            next.Sources.RemoveAll(item =>
                string.Equals(item.OwnerSid, source.OwnerSid, StringComparison.Ordinal) &&
                string.Equals(item.ConversationId, source.ConversationId, StringComparison.Ordinal) &&
                string.Equals(item.SourceId, source.SourceId, StringComparison.Ordinal));
            next.Sources.Add(new SourceDocument
            {
                OwnerSid = source.OwnerSid,
                ConversationId = source.ConversationId,
                SourceId = source.SourceId,
                FileName = Path.GetFileName(source.FileName),
                SourceIdentitySha256 = source.SourceIdentitySha256.ToLowerInvariant(),
                Chunks = storedChunks
            });
            SaveIndex(next);
            return storedChunks.Count;
        }
        finally { _processGate.Release(); }
    }

    /// <summary>Embeds a query with the same model and returns cosine-ranked citations.</summary>
    public async Task<IReadOnlyList<RagSearchResult>> SearchAsync(
        string ownerSid,
        string conversationId,
        string query,
        int topK = 5,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ValidateOwnerSid(ownerSid);
        ValidateConversationId(conversationId);
        ArgumentException.ThrowIfNullOrWhiteSpace(query);
        if (query.Length > 16_000) throw new ArgumentException("RAG query is too long.", nameof(query));
        if (topK is < 1 or > MaximumResults) throw new ArgumentOutOfRangeException(nameof(topK));
        cancellationToken.ThrowIfCancellationRequested();

        await _processGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var snapshot = LoadIndex();
            var snapshotSources = snapshot.Sources.Where(source =>
                    string.Equals(source.OwnerSid, ownerSid, StringComparison.Ordinal) &&
                    string.Equals(source.ConversationId, conversationId, StringComparison.Ordinal))
                .ToArray();
            if (snapshotSources.Length == 0) return [];
            foreach (var source in snapshotSources) ValidateStoredSource(source);
        }
        finally { _processGate.Release(); }

        var queryVector = (await EmbedBatchesAsync([query], cancellationToken).ConfigureAwait(false))[0];
        await _processGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var index = LoadIndex();
            var scopedSources = index.Sources
                .Where(source =>
                    string.Equals(source.OwnerSid, ownerSid, StringComparison.Ordinal) &&
                    string.Equals(source.ConversationId, conversationId, StringComparison.Ordinal))
                .ToArray();
            if (scopedSources.Length == 0) return [];
            EnsureCompatible(index, queryVector.Length);
            foreach (var source in scopedSources) ValidateStoredSource(source);
            foreach (var chunk in scopedSources.SelectMany(source => source.Chunks))
            {
                if (chunk.Text is null || chunk.ChunkSha256 is null ||
                    !string.Equals(chunk.ChunkSha256, Sha256(chunk.Text), StringComparison.Ordinal))
                    throw new InvalidDataException("RAG indexed chunk SHA-256 does not match its text.");
                if (chunk.ChunkIndex < 0 || chunk.Vector is null || chunk.Vector.Length != queryVector.Length ||
                    chunk.Vector.Any(value => !float.IsFinite(value)))
                    throw new InvalidDataException("RAG indexed embedding is invalid or has incompatible dimensions.");
            }

            return scopedSources
                .SelectMany(source => source.Chunks.Select(chunk => new RagSearchResult(
                    source.OwnerSid,
                    source.ConversationId,
                    source.SourceId,
                    source.FileName,
                    source.SourceIdentitySha256,
                    chunk.ChunkSha256,
                    chunk.ChunkIndex,
                    CosineSimilarity(queryVector, chunk.Vector),
                    chunk.Text)))
                .OrderByDescending(result => result.Score)
                .Take(topK)
                .ToArray();
        }
        finally { _processGate.Release(); }
    }

    /// <summary>Deletes an indexed source by its stable host-assigned identifier.</summary>
    public async Task<bool> DeleteSourceAsync(string ownerSid, string conversationId, string sourceId, CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ValidateOwnerSid(ownerSid);
        ValidateConversationId(conversationId);
        ValidateSourceId(sourceId);
        await _processGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            using var indexLock = await AcquireIndexLockAsync(cancellationToken).ConfigureAwait(false);
            var current = LoadIndex();
            var next = CloneIndex(current);
            var removed = next.Sources.RemoveAll(item =>
                string.Equals(item.OwnerSid, ownerSid, StringComparison.Ordinal) &&
                string.Equals(item.ConversationId, conversationId, StringComparison.Ordinal) &&
                string.Equals(item.SourceId, sourceId, StringComparison.Ordinal));
            if (removed == 0) return false;
            SaveIndex(next);
            return true;
        }
        finally { _processGate.Release(); }
    }

    /// <summary>Deletes all indexed sources owned by one conversation.</summary>
    public async Task<int> DeleteConversationAsync(string ownerSid, string conversationId, CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ValidateOwnerSid(ownerSid);
        ValidateConversationId(conversationId);
        await _processGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            using var indexLock = await AcquireIndexLockAsync(cancellationToken).ConfigureAwait(false);
            var current = LoadIndex();
            var next = CloneIndex(current);
            var removed = next.Sources.RemoveAll(item =>
                string.Equals(item.OwnerSid, ownerSid, StringComparison.Ordinal) &&
                string.Equals(item.ConversationId, conversationId, StringComparison.Ordinal));
            if (removed == 0) return 0;
            SaveIndex(next);
            return removed;
        }
        finally { _processGate.Release(); }
    }

    /// <summary>
    /// Formats retrieved passages with stable citations for a local chat prompt.
    /// Treat the returned text as untrusted reference data; the caller must tell the
    /// model never to follow instructions found inside retrieved passages.
    /// </summary>
    public static string BuildContext(IReadOnlyList<RagSearchResult> results, int maxCharacters = 24_000)
    {
        ArgumentNullException.ThrowIfNull(results);
        if (maxCharacters is < 256 or > 128_000)
            throw new ArgumentOutOfRangeException(nameof(maxCharacters));

        var context = new StringBuilder(Math.Min(maxCharacters, 4096));
        foreach (var result in results)
        {
            if (result is null || string.IsNullOrWhiteSpace(result.Text)) continue;
            var citation = $"[SOURCE: {Uri.EscapeDataString(result.FileName)}#{result.ChunkIndex + 1}; SHA256:{result.ChunkSha256}]";
            var required = citation.Length + result.Text.Length + 2;
            if (context.Length + required > maxCharacters)
            {
                var available = maxCharacters - context.Length - citation.Length - 4;
                if (available > 0)
                    context.Append(citation).Append('\n').Append(result.Text.AsSpan(0, Math.Min(available, result.Text.Length))).Append("…\n\n");
                break;
            }
            context.Append(citation).Append('\n').Append(result.Text).Append("\n\n");
        }
        return context.ToString().TrimEnd();
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _http.Dispose();
        _processGate.Dispose();
    }

    private async Task<List<float[]>> EmbedBatchesAsync(IReadOnlyList<string> inputs, CancellationToken cancellationToken)
    {
        var vectors = new List<float[]>(inputs.Count);
        for (var offset = 0; offset < inputs.Count; offset += EmbeddingBatchSize)
        {
            var batchLength = Math.Min(EmbeddingBatchSize, inputs.Count - offset);
            var batch = new string[batchLength];
            for (var index = 0; index < batchLength; index++) batch[index] = inputs[offset + index];
            using var requestCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            requestCts.CancelAfter(EmbeddingRequestTimeout);
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, _embedEndpoint)
                {
                    Content = JsonContent.Create(
                        new { model = _model, input = batch, truncate = false },
                        options: JsonOptions)
                };
                using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, requestCts.Token)
                    .ConfigureAwait(false);
                var responseUri = response.RequestMessage?.RequestUri;
                if (responseUri is null || !IsLoopbackHttp(responseUri) || responseUri.Port != _embedEndpoint.Port ||
                    !string.Equals(responseUri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase))
                    throw new HttpRequestException("Ollama embedding response escaped the configured loopback endpoint.");
                if (!response.IsSuccessStatusCode)
                    throw new HttpRequestException($"Local Ollama embedding request failed with HTTP {(int)response.StatusCode}.");

                var body = await ReadBoundedBodyAsync(response.Content, 16 * 1024 * 1024, requestCts.Token).ConfigureAwait(false);
                using var json = JsonDocument.Parse(body, new JsonDocumentOptions { MaxDepth = 8 });
                if (!json.RootElement.TryGetProperty("embeddings", out var embeddingList) ||
                    embeddingList.ValueKind != JsonValueKind.Array || embeddingList.GetArrayLength() != batch.Length)
                    throw new InvalidDataException("Ollama returned an invalid embeddings array.");

                foreach (var embedding in embeddingList.EnumerateArray())
                    vectors.Add(ParseVector(embedding));
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                throw new TimeoutException("Local Ollama embedding request timed out.");
            }
        }

        if (vectors.Count != inputs.Count || vectors.Count == 0)
            throw new InvalidDataException("Ollama returned an incomplete embedding batch.");
        var dimensions = vectors[0].Length;
        if (dimensions == 0 || vectors.Any(vector => vector.Length != dimensions))
            throw new InvalidDataException("Ollama returned vectors with inconsistent dimensions.");
        return vectors;
    }

    private static async Task<byte[]> ReadBoundedBodyAsync(HttpContent content, int maxBytes, CancellationToken cancellationToken)
    {
        if (content.Headers.ContentLength is long length && length > maxBytes)
            throw new InvalidDataException("Ollama embedding response exceeds the configured size limit.");
        await using var input = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using var output = new MemoryStream(Math.Min(maxBytes, 64 * 1024));
        var buffer = new byte[16 * 1024];
        while (true)
        {
            var read = await input.ReadAsync(buffer.AsMemory(0, buffer.Length), cancellationToken).ConfigureAwait(false);
            if (read == 0) break;
            if (output.Length + read > maxBytes)
                throw new InvalidDataException("Ollama embedding response exceeds the configured size limit.");
            output.Write(buffer, 0, read);
        }
        return output.ToArray();
    }

    private static float[] ParseVector(JsonElement item)
    {
        if (item.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Ollama embedding is not a vector.");
        var dimensions = item.GetArrayLength();
        if (dimensions is < 1 or > MaximumEmbeddingDimensions)
            throw new InvalidDataException("Ollama embedding has an unsupported vector dimension count.");
        var result = new float[dimensions];
        var index = 0;
        double normSquared = 0;
        foreach (var value in item.EnumerateArray())
        {
            if (!value.TryGetSingle(out var number) || !float.IsFinite(number))
                throw new InvalidDataException("Ollama embedding contains a non-finite value.");
            result[index++] = number;
            normSquared += (double)number * number;
        }
        var norm = Math.Sqrt(normSquared);
        if (!double.IsFinite(norm) || norm <= 0) throw new InvalidDataException("Ollama returned a zero-length embedding.");
        for (var i = 0; i < result.Length; i++) result[i] = (float)(result[i] / norm);
        return result;
    }

    // This per-instance gate handles local ordering; the file lock serializes read-modify-write
    // transactions across multiple NOX processes sharing the same index file.
    private async Task<FileStream> AcquireIndexLockAsync(CancellationToken cancellationToken)
    {
        var directory = Path.GetDirectoryName(_indexPath)!;
        Directory.CreateDirectory(directory);
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("RAG index directory cannot be a reparse point.");

        var lockPath = _indexPath + ".lock";
        var contentionStarted = Environment.TickCount64;
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (File.Exists(lockPath) && (File.GetAttributes(lockPath) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("RAG index lock cannot be a reparse point.");
            try
            {
                return new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            }
            catch (IOException exception) when (IsLockContention(exception) &&
                Environment.TickCount64 - contentionStarted < 30_000)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(50), cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private static bool IsLockContention(IOException exception) =>
        (exception.HResult & 0xFFFF) is 11 or 32 or 33;

    private IndexDocument LoadIndex()
    {
        if (!File.Exists(_indexPath)) return new IndexDocument { Model = _model };
        if ((File.GetAttributes(_indexPath) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("RAG index cannot be a reparse point.");
        using var stream = new FileStream(_indexPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > MaximumIndexFileBytes)
            throw new InvalidDataException("RAG index exceeds the configured size limit.");
        // The Python RAG owner rejects duplicate nested provenance keys.
        // .NET 8's Web JSON deserializer otherwise silently accepts the last
        // case-insensitive alias (OwnerSid/ownerSid included). Validate the
        // existing on-disk index first; never rewrite a suspicious source.
        using (var parsed = JsonDocument.Parse(stream, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 64
        }))
        {
            var pending = new Stack<JsonElement>();
            pending.Push(parsed.RootElement);
            while (pending.Count > 0)
            {
                var node = pending.Pop();
                if (node.ValueKind == JsonValueKind.Object)
                {
                    var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach (var property in node.EnumerateObject())
                    {
                        if (!seen.Add(property.Name))
                            throw new InvalidDataException("RAG index has ambiguous duplicate JSON property.");
                        pending.Push(property.Value);
                    }
                }
                else if (node.ValueKind == JsonValueKind.Array)
                {
                    foreach (var element in node.EnumerateArray())
                        pending.Push(element);
                }
            }
        }
        stream.Position = 0;
        var loaded = JsonSerializer.Deserialize<IndexDocument>(stream, JsonOptions)
            ?? throw new InvalidDataException("RAG index is empty or invalid.");
        if (!string.Equals(loaded.Schema, IndexSchema, StringComparison.Ordinal) || loaded.Sources is null ||
            loaded.Sources.Any(source => source is null || source.Chunks is null ||
                source.Chunks.Any(chunk => chunk is null || chunk.Vector is null)))
            throw new InvalidDataException("RAG index schema is unsupported.");
        return loaded;
    }

    private void SaveIndex(IndexDocument index)
    {
        var directory = Path.GetDirectoryName(_indexPath)!;
        Directory.CreateDirectory(directory);
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("RAG index directory cannot be a reparse point.");

        var temporary = _indexPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                       64 * 1024, FileOptions.WriteThrough))
            {
                JsonSerializer.Serialize(stream, index, JsonOptions);
                if (stream.Length > MaximumIndexFileBytes)
                    throw new InvalidDataException("RAG index would exceed the configured size limit.");
                stream.Flush(flushToDisk: true);
            }
            if (File.Exists(_indexPath) && (File.GetAttributes(_indexPath) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("RAG index cannot be a reparse point.");
            File.Move(temporary, _indexPath, overwrite: true);
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch { }
        }
    }

    private void EnsureCompatible(IndexDocument index, int dimensions)
    {
        if (index.Sources.Count == 0)
        {
            index.Model = _model;
            index.VectorDimensions = dimensions;
            return;
        }
        if (!string.Equals(index.Model, _model, StringComparison.Ordinal) || index.VectorDimensions != dimensions)
            throw new InvalidOperationException("RAG index uses a different embedding model or vector size; rebuild it explicitly before changing models.");
    }

    private static IndexDocument CloneIndex(IndexDocument source) => new()
    {
        Schema = source.Schema,
        Model = source.Model,
        VectorDimensions = source.VectorDimensions,
        // Mutations below change only the source collection and top-level index metadata.
        // Reuse immutable-for-this-operation source/chunk records to avoid duplicating a large index.
        Sources = source.Sources.ToList()
    };

    private static List<string> SplitIntoChunks(string text)
    {
        var chunks = new List<string>();
        var position = 0;
        while (position < text.Length)
        {
            var end = Math.Min(position + ChunkCharacters, text.Length);
            if (end < text.Length)
            {
                var boundary = text.LastIndexOfAny([' ', '\n', '\r', '\t'], end - 1, end - position);
                if (boundary > position + ChunkCharacters / 2) end = boundary;
            }
            var chunk = text[position..end].Trim();
            if (chunk.Length > 0) chunks.Add(chunk);
            if (end >= text.Length) break;
            position = Math.Max(position + 1, end - ChunkOverlap);
        }
        return chunks;
    }

    private static double CosineSimilarity(IReadOnlyList<float> left, IReadOnlyList<float> right)
    {
        if (left.Count != right.Count) throw new InvalidDataException("Stored embedding dimensions do not match.");
        double dot = 0;
        double leftNormSquared = 0;
        double rightNormSquared = 0;
        for (var i = 0; i < left.Count; i++)
        {
            dot += left[i] * right[i];
            leftNormSquared += left[i] * left[i];
            rightNormSquared += right[i] * right[i];
        }
        if (leftNormSquared <= 0 || rightNormSquared <= 0)
            throw new InvalidDataException("RAG query or indexed embedding has zero magnitude.");
        return Math.Clamp(dot / Math.Sqrt(leftNormSquared * rightNormSquared), -1d, 1d);
    }

    private static void ValidateSource(RagSourceDocument source)
    {
        ArgumentNullException.ThrowIfNull(source);
        ValidateOwnerSid(source.OwnerSid);
        ValidateConversationId(source.ConversationId);
        ValidateSourceId(source.SourceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(source.FileName);
        ArgumentNullException.ThrowIfNull(source.Text);
        if (source.FileName.Length > 255 || source.FileName.Any(char.IsControl) ||
            source.FileName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
            !string.Equals(Path.GetFileName(source.FileName), source.FileName, StringComparison.Ordinal))
            throw new ArgumentException("RAG source filename must be a plain filename of at most 255 printable characters.", nameof(source));
        if (!IsSha256(source.SourceIdentitySha256))
            throw new ArgumentException("RAG source identity must be a SHA-256 hex digest.", nameof(source));
    }

    private static void ValidateStoredSource(SourceDocument source)
    {
        try
        {
            ValidateOwnerSid(source.OwnerSid);
            ValidateConversationId(source.ConversationId);
            ValidateSourceId(source.SourceId);
        }
        catch (ArgumentException exception)
        {
            throw new InvalidDataException("RAG indexed source identity is invalid.", exception);
        }

        if (string.IsNullOrWhiteSpace(source.FileName) || source.FileName.Length > 255 ||
            source.FileName.Any(char.IsControl) || source.FileName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
            !string.Equals(Path.GetFileName(source.FileName), source.FileName, StringComparison.Ordinal) ||
            !IsSha256(source.SourceIdentitySha256))
            throw new InvalidDataException("RAG indexed source citation metadata is invalid.");
    }

    private static bool IsSha256(string? value) => value is { Length: 64 } && value.All(Uri.IsHexDigit);

    private static void ValidateSourceId(string sourceId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceId);
        if (sourceId.Length > MaximumSourceIdCharacters || sourceId.Any(char.IsControl))
            throw new ArgumentException($"Source ID must be at most {MaximumSourceIdCharacters} printable characters.", nameof(sourceId));
    }

    internal static void ValidateConversationId(string conversationId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);
        if (conversationId.Length > 256 || conversationId.Any(char.IsControl))
            throw new ArgumentException("Conversation ID must be at most 256 printable characters.", nameof(conversationId));
    }

    internal static void ValidateOwnerSid(string ownerSid)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(ownerSid);
        var parts = ownerSid.Split('-');
        if (ownerSid.Length > 184 || parts.Length is < 4 or > 18 ||
            !string.Equals(parts[0], "S", StringComparison.Ordinal) || parts[1] != "1" ||
            !ulong.TryParse(parts[2], NumberStyles.None, CultureInfo.InvariantCulture, out var authority) ||
            authority > 0xFFFFFFFFFFFFUL)
            throw new ArgumentException("Owner must be a valid Windows SID string.", nameof(ownerSid));

        for (var i = 3; i < parts.Length; i++)
        {
            if (!uint.TryParse(parts[i], NumberStyles.None, CultureInfo.InvariantCulture, out var subAuthority))
                throw new ArgumentException("Owner must be a valid Windows SID string.", nameof(ownerSid));
        }
    }

    private static bool IsLoopbackHttp(Uri uri) => uri.IsAbsoluteUri && uri.Scheme == Uri.UriSchemeHttp &&
        (uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) || IPAddress.TryParse(uri.Host, out var address) && IPAddress.IsLoopback(address));

    private static string ResolveIndexPath(string? indexPath)
    {
        if (indexPath is null)
        {
            var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (string.IsNullOrWhiteSpace(local))
                throw new InvalidOperationException("Local application data directory is unavailable.");
            indexPath = Path.Combine(local, "NOX_HELION_Integrator", "RAG", "index-v1.json");
        }
        else if (string.IsNullOrWhiteSpace(indexPath) || !Path.IsPathFullyQualified(indexPath))
        {
            throw new ArgumentException("RAG index path must be a non-empty absolute path.", nameof(indexPath));
        }

        var fullPath = Path.GetFullPath(indexPath);
        if (string.IsNullOrWhiteSpace(Path.GetFileName(fullPath)) ||
            !string.Equals(Path.GetExtension(fullPath), ".json", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("RAG index path must name a JSON file.", nameof(indexPath));
        if (Directory.Exists(fullPath))
            throw new ArgumentException("RAG index path points to a directory.", nameof(indexPath));
        if (File.Exists(fullPath) && (File.GetAttributes(fullPath) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("RAG index cannot be a reparse point.");

        var parent = Path.GetDirectoryName(fullPath);
        if (parent is null) throw new ArgumentException("RAG index path has no parent directory.", nameof(indexPath));
        if (Directory.Exists(parent) && (File.GetAttributes(parent) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("RAG index directory cannot be a reparse point.");
        return fullPath;
    }

    private static string Sha256(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private sealed class IndexDocument
    {
        public IndexDocument() { }
        public string Schema { get; set; } = IndexSchema;
        public string Model { get; set; } = string.Empty;
        public int VectorDimensions { get; set; }
        public List<SourceDocument> Sources { get; set; } = [];
    }

    private sealed class SourceDocument
    {
        public SourceDocument() { }
        public string OwnerSid { get; set; } = string.Empty;
        public string ConversationId { get; set; } = string.Empty;
        public string SourceId { get; set; } = string.Empty;
        public string FileName { get; set; } = string.Empty;
        public string SourceIdentitySha256 { get; set; } = string.Empty;
        public List<ChunkDocument> Chunks { get; set; } = [];
    }

    private sealed class ChunkDocument
    {
        public ChunkDocument() { }
        public int ChunkIndex { get; set; }
        public string ChunkSha256 { get; set; } = string.Empty;
        public string Text { get; set; } = string.Empty;
        public float[] Vector { get; set; } = [];
    }
}
