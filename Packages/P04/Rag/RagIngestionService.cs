using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace NoxP04.Rag;

/// <summary>Receipt for one source import or idempotent update.</summary>
public sealed record RagIngestionReceipt(
    string SourceId,
    string FileName,
    string SourceIdentitySha256,
    int IndexedChunks);

/// <summary>Bounded retrieval context plus the exact chunks used to build it.</summary>
public sealed record RagContextResult(
    string ContextText,
    IReadOnlyList<RagSearchResult> Sources);

/// <summary>
/// File and text intake in front of RagService. This class does not authorize a
/// user or choose files; the host must do that first and provide the Windows SID
/// and conversation ID. Only local UTF-8 TXT/Markdown is accepted. Re-ingesting
/// the same full path upserts the existing source, so changed files replace old
/// chunks instead of accumulating duplicates.
/// </summary>
public sealed class RagIngestionService
{
    private const int MaximumFileBytes = 8 * 1024 * 1024;
    private const int MaximumTextCharacters = 2_000_000;
    private const int MaximumContextCharacters = 24_000;
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private static readonly HashSet<string> SupportedExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".txt", ".md"
    };

    private readonly RagService _rag;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public RagIngestionService(RagService rag)
    {
        _rag = rag ?? throw new ArgumentNullException(nameof(rag));
    }

    /// <summary>
    /// Imports or updates a local file. The stable source ID is derived from the
    /// canonical path; the content SHA changes on every revision.
    /// </summary>
    public async Task<RagIngestionReceipt> IngestFileAsync(
        string ownerSid,
        string conversationId,
        string filePath,
        CancellationToken cancellationToken = default)
    {
        ValidateScope(ownerSid, conversationId);
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);
        var fullPath = Path.GetFullPath(filePath);
        if (!Path.IsPathFullyQualified(fullPath) || IsNetworkPath(fullPath))
            throw new IOException("RAG imports must come from a fully qualified local path.");

        var extension = Path.GetExtension(fullPath);
        if (!SupportedExtensions.Contains(extension))
            throw new InvalidDataException("RAG accepts only .txt and .md files.");
        RejectReparsePath(fullPath);

        await using var input = new FileStream(
            fullPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 64 * 1024,
            options: FileOptions.Asynchronous | FileOptions.SequentialScan);
        if (input.Length is <= 0 or > MaximumFileBytes)
            throw new InvalidDataException("RAG file size must be between 1 byte and 8 MiB.");

        var bytes = new byte[checked((int)input.Length)];
        await input.ReadExactlyAsync(bytes, cancellationToken).ConfigureAwait(false);
        var extra = new byte[1];
        if (await input.ReadAsync(extra.AsMemory(0, 1), cancellationToken).ConfigureAwait(false) != 0)
            throw new IOException("RAG source changed while it was being read.");

        var text = DecodeUtf8(bytes);
        var sourceId = StableFileSourceId(fullPath);
        return await IngestBytesAsync(
            ownerSid,
            conversationId,
            sourceId,
            Path.GetFileName(fullPath),
            bytes,
            text,
            cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Imports bytes already staged by the host. The source SHA is computed here
    /// from the original bytes, before text decoding, to preserve provenance.
    /// </summary>
    public async Task<RagIngestionReceipt> IngestBytesAsync(
        string ownerSid,
        string conversationId,
        string sourceId,
        string fileName,
        ReadOnlyMemory<byte> content,
        CancellationToken cancellationToken = default)
    {
        ValidateScope(ownerSid, conversationId);
        ValidateSourceMetadata(sourceId, fileName);
        if (content.Length is <= 0 or > MaximumFileBytes)
            throw new InvalidDataException("RAG content size must be between 1 byte and 8 MiB.");
        if (!SupportedExtensions.Contains(Path.GetExtension(fileName)))
            throw new InvalidDataException("RAG accepts only .txt and .md files.");

        var bytes = content.ToArray();
        var text = DecodeUtf8(bytes);
        return await IngestBytesAsync(ownerSid, conversationId, sourceId, fileName, bytes, text, cancellationToken)
            .ConfigureAwait(false);
    }

    /// <summary>
    /// Imports caller-extracted text and computes identity over its UTF-8 bytes.
    /// Use IngestBytesAsync when the original payload bytes are available.
    /// </summary>
    public async Task<RagIngestionReceipt> IngestTextAsync(
        string ownerSid,
        string conversationId,
        string sourceId,
        string fileName,
        string text,
        CancellationToken cancellationToken = default)
    {
        ValidateScope(ownerSid, conversationId);
        ValidateSourceMetadata(sourceId, fileName);
        ArgumentNullException.ThrowIfNull(text);
        if (text.Length is 0 or > MaximumTextCharacters || string.IsNullOrWhiteSpace(text))
            throw new InvalidDataException("RAG text is empty or exceeds the supported character limit.");

        var bytes = StrictUtf8.GetBytes(text);
        if (bytes.Length > MaximumFileBytes)
            throw new InvalidDataException("RAG text exceeds the 8 MiB source limit.");
        return await IngestBytesAsync(ownerSid, conversationId, sourceId, fileName, bytes, text, cancellationToken)
            .ConfigureAwait(false);
    }

    /// <summary>Deletes one source within the exact owner and conversation scope.</summary>
    public Task<bool> DeleteSourceAsync(
        string ownerSid,
        string conversationId,
        string sourceId,
        CancellationToken cancellationToken = default)
    {
        ValidateScope(ownerSid, conversationId);
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceId);
        return _rag.DeleteSourceAsync(ownerSid, conversationId, sourceId, cancellationToken);
    }

    /// <summary>Deletes all indexed sources within the exact owner and conversation scope.</summary>
    public Task<int> DeleteConversationAsync(
        string ownerSid,
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        ValidateScope(ownerSid, conversationId);
        return _rag.DeleteConversationAsync(ownerSid, conversationId, cancellationToken);
    }

    /// <summary>
    /// Retrieves real embedding matches and formats bounded citations for the
    /// host's model context. Retrieved text remains untrusted input; the host must
    /// tell its model not to execute instructions found inside these passages.
    /// </summary>
    public async Task<RagContextResult> BuildContextAsync(
        string ownerSid,
        string conversationId,
        string query,
        int topK = 5,
        CancellationToken cancellationToken = default)
    {
        ValidateScope(ownerSid, conversationId);
        ArgumentException.ThrowIfNullOrWhiteSpace(query);
        var hits = await _rag.SearchAsync(ownerSid, conversationId, query, topK, cancellationToken)
            .ConfigureAwait(false);

        var context = new StringBuilder(Math.Min(MaximumContextCharacters, hits.Sum(hit => hit.Text.Length)));
        var included = new List<RagSearchResult>(hits.Count);
        foreach (var hit in hits)
        {
            var citation = $"[SOURCE: {Uri.EscapeDataString(hit.FileName)}#{hit.ChunkIndex + 1}; SHA256:{hit.ChunkSha256}]\n";
            var needed = citation.Length + hit.Text.Length + (context.Length == 0 ? 0 : 2);
            if (needed > MaximumContextCharacters - context.Length)
                break;
            if (context.Length > 0) context.Append("\n\n");
            context.Append(citation).Append(hit.Text);
            included.Add(hit);
        }
        return new RagContextResult(context.ToString(), included);
    }

    private async Task<RagIngestionReceipt> IngestBytesAsync(
        string ownerSid,
        string conversationId,
        string sourceId,
        string fileName,
        byte[] bytes,
        string text,
        CancellationToken cancellationToken)
    {
        if (text.Length > MaximumTextCharacters || string.IsNullOrWhiteSpace(text))
            throw new InvalidDataException("RAG decoded text is empty or exceeds the supported character limit.");

        var sha256 = Sha256(bytes);
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var chunks = await _rag.IngestTextAsync(
                new RagSourceDocument(ownerSid, conversationId, sourceId, Path.GetFileName(fileName), sha256, text),
                cancellationToken).ConfigureAwait(false);
            return new RagIngestionReceipt(sourceId, Path.GetFileName(fileName), sha256, chunks);
        }
        finally
        {
            _gate.Release();
        }
    }

    private static string DecodeUtf8(byte[] bytes)
    {
        try
        {
            var text = StrictUtf8.GetString(bytes);
            if (text.Length > 0 && text[0] == '\uFEFF') text = text[1..];
            if (text.IndexOf('\0') >= 0)
                throw new InvalidDataException("RAG text contains a NUL character.");
            return text;
        }
        catch (DecoderFallbackException exception)
        {
            throw new InvalidDataException("RAG accepts only valid UTF-8 text.", exception);
        }
    }

    private static string StableFileSourceId(string fullPath)
    {
        var identityPath = OperatingSystem.IsWindows() ? fullPath.ToUpperInvariant() : fullPath;
        return "file:" + Sha256(StrictUtf8.GetBytes(identityPath));
    }

    private static string Sha256(byte[] bytes) =>
        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static bool IsNetworkPath(string path) =>
        path.StartsWith("\\\\", StringComparison.Ordinal) ||
        path.StartsWith("//", StringComparison.Ordinal);

    private static void RejectReparsePath(string fullPath)
    {
        var current = fullPath;
        while (!string.IsNullOrEmpty(current))
        {
            var attributes = File.GetAttributes(current);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("RAG does not follow symbolic links or reparse points.");
            var parent = Directory.GetParent(current);
            if (parent is null) break;
            current = parent.FullName;
        }
        if ((File.GetAttributes(fullPath) & FileAttributes.Directory) != 0)
            throw new IOException("RAG source must be a regular file.");
    }

    private static void ValidateScope(string ownerSid, string conversationId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(ownerSid);
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);
        if (!ownerSid.StartsWith("S-1-", StringComparison.Ordinal) || ownerSid.Length > 184 || ownerSid.Any(char.IsControl))
            throw new ArgumentException("A valid Windows owner SID is required.", nameof(ownerSid));
        if (conversationId.Length > 256 || conversationId.Any(char.IsControl))
            throw new ArgumentException("Conversation ID is invalid or too long.", nameof(conversationId));
    }

    private static void ValidateSourceMetadata(string sourceId, string fileName)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceId);
        ArgumentException.ThrowIfNullOrWhiteSpace(fileName);
        if (sourceId.Length > 256 || sourceId.Any(char.IsControl))
            throw new ArgumentException("Source ID is invalid or too long.", nameof(sourceId));
        if (fileName.Length > 255 || fileName.Any(char.IsControl) ||
            fileName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
            !string.Equals(Path.GetFileName(fileName), fileName, StringComparison.Ordinal))
            throw new ArgumentException("Source name must be a plain filename.", nameof(fileName));
        if (!SupportedExtensions.Contains(Path.GetExtension(fileName)))
            throw new InvalidDataException("RAG accepts only .txt and .md files.");
    }
}
