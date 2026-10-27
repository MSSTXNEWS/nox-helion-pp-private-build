// NOX PACK01: chat.rag routes through ORIGINAL P04 citation-bearing RAG provider.
// Owner #2 chat route, no duplicate embedding index, database, LLM or network server.
using NoxP04.Rag;

namespace Nox.Pack01;

public sealed record NativeP02ChatScope(string WindowsSid, string ConversationId,
    string SessionId);

public sealed class P02RagChatOwnerPort
{
    private readonly IRagChatContextProvider _existingP04;
    private readonly Func<NativeP02ChatScope,bool> _authorizeNativeSession;

    public P02RagChatOwnerPort(IRagChatContextProvider originalRagContext,
        Func<NativeP02ChatScope,bool> authorizeNativeSession)
    {
        _existingP04 = originalRagContext ??
            throw new ArgumentNullException(nameof(originalRagContext));
        _authorizeNativeSession = authorizeNativeSession ??
            throw new ArgumentNullException(nameof(authorizeNativeSession));
    }

    public async Task<RagContextResult> RetrieveAsync(NativeP02ChatScope nativeScope,
        string userMessage, int topK=5, CancellationToken stop=default)
    {
        if (nativeScope is null ||
            string.IsNullOrWhiteSpace(nativeScope.WindowsSid) ||
            string.IsNullOrWhiteSpace(nativeScope.ConversationId) ||
            string.IsNullOrWhiteSpace(nativeScope.SessionId))
            throw new UnauthorizedAccessException("Authenticated original NOX host scope missing");

        // This decision is a trusted native host predicate, never from a WebView page.
        if (_authorizeNativeSession(nativeScope) is not true)
            throw new UnauthorizedAccessException("Native NOX session not authorized");

        if (string.IsNullOrWhiteSpace(userMessage) || userMessage.Length > 16000)
            throw new ArgumentException("Bounded chat search text required",nameof(userMessage));
        if (topK is <1 or >20)
            throw new ArgumentOutOfRangeException(nameof(topK));
        stop.ThrowIfCancellationRequested();

        var result=await _existingP04.RetrieveAsync(nativeScope.WindowsSid,
            nativeScope.ConversationId,userMessage,topK,stop).ConfigureAwait(false);

        // Defensive validation against a misconfigured embedding provider/owner.
        if (result is null || result.ContextText.Length > 24000 ||
            result.Sources.Any(x=>x.OwnerSid != nativeScope.WindowsSid ||
                                  x.ConversationId != nativeScope.ConversationId))
            throw new InvalidDataException("RAG owner scope mismatch or response out of bounds");

        // This is evidence for the user's existing chat, never a system-level instruction.
        // The original P02 host must add it as untrusted context and show real citations.
        return result;
    }
}
