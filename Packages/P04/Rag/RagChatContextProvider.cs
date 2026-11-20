using System;
using System.Threading;
using System.Threading.Tasks;

namespace NoxP04.Rag;

/// <summary>
/// Small host-facing seam for the live chat pipeline. Register this alongside
/// RagIngestionService and call RetrieveAsync before composing a turn. The chat
/// host must pass ContextText as untrusted evidence (not as system instructions)
/// and render Sources as citations. This type does not own authentication,
/// conversation storage, prompt policy, or model transport.
/// </summary>
public interface IRagChatContextProvider
{
    Task<RagContextResult> RetrieveAsync(
        string authenticatedOwnerSid,
        string conversationId,
        string userMessage,
        int topK = 5,
        CancellationToken cancellationToken = default);
}

/// <summary>Adapts the bounded, citation-bearing retrieval API to a chat turn.</summary>
public sealed class RagChatContextProvider : IRagChatContextProvider
{
    private readonly RagIngestionService _ingestion;

    public RagChatContextProvider(RagIngestionService ingestion)
    {
        _ingestion = ingestion ?? throw new ArgumentNullException(nameof(ingestion));
    }

    public Task<RagContextResult> RetrieveAsync(
        string authenticatedOwnerSid,
        string conversationId,
        string userMessage,
        int topK = 5,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(authenticatedOwnerSid);
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);
        ArgumentException.ThrowIfNullOrWhiteSpace(userMessage);
        if (topK is < 1 or > 20)
            throw new ArgumentOutOfRangeException(nameof(topK), "RAG topK must be between 1 and 20.");

        // Owner SID must be derived by the authenticated host, never from chat input.
        return _ingestion.BuildContextAsync(
            authenticatedOwnerSid,
            conversationId,
            userMessage,
            topK,
            cancellationToken);
    }
}
