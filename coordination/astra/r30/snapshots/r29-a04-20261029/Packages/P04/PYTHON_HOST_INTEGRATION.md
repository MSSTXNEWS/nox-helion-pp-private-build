# P04 -> P02 Python host: one RAG, one chat, no second server

RunID NOX-V16-E04-UNIFIED-20261028. Owner P04 source #4; single host/SourceLock integration #6.
Status: candidate. This file never claims native Windows integration or a real GPU run.

## Why this bridge exists
P02's preferred chat candidate is Python ChatBridge in PR #13.
P04 RagService.cs is a .NET8 owner candidate and cannot be silently used by an
existing Python/PyInstaller host. The file rag_python_compat.py is a **port**
of the same local RAG index and Ollama /api/embed contract, not an additional
model, chat, search server or database. E06 MUST select exactly ONE RAG runtime:
canonical existing original host when present; Python port only if needed; or
the verified C# service if the actual frozen host is .NET8. Never run both on
the same index concurrently.

## Exact adapter for the already-existing P02 ChatBridge
In the host-selected runtime, use its existing authenticated tenant/principal
and conversation IDs. Do not derive owner SID from untrusted browser fields.

    from rag_python_compat import LocalRag, p02_callback
    from p02_chat_bridge import ChatBridge

    rag = LocalRag("http://127.0.0.1:11434/", APPROVED_INSTALLED_EMBED_MODEL,
                   APPROVED_LOCAL_INDEX_PATH)
    context = p02_callback(rag, existing_trusted_host_sid_mapper)
    existing_chat = ChatBridge(existing_store, existing_ollama, rag_context=context)

The P02 bridge first enforces its own chat history ownership ACL. The mapper
must return the Windows SID authorized by the native host for that authenticated
tenant/principal, not a user-supplied SID string. Existing chat.streaming,
SQLite, attachments and STOP remain owned by P02; only the existing
rag_context seam is supplied by P04. RAG excerpts are untrusted reference data.
The P02 bridge's source-rendering contract accepts max 128-char source_id and
200-char title; this adapter fails closed on incompatible legacy metadata
instead of quietly supplying uncited excerpts.

## Source file handling
Only an already-allowed absolute local .txt/.md path supplied by native picker:
    rag.ingest_file(trusted_sid, existing_chat_id, native_authorized_path)

No OCR, PDF, DOCX, online downloads or external file system mounts are silently
enabled. An unchanged canonical file/source revision avoids a duplicate
Ollama embedding request. Changes upsert by stable file path identity, and
delete calls preserve the same exact owner/conversation scope. Index schema:
NOX-RAG-INDEX-v1; bounded atomic JSON writes; SHA-256 source and chunk identities;
no additional SQLite file. Never auto-migrate or overwrite the current user's
existing RAG data without an approved SourceLock and backup.

## Tests, permitted completion
GitHub CI uses loopback synthetic /api/embed fixture, not installed Ollama
weights. On the actual Windows host, after owner has installed an approved
licensed embedding model, run the existing opt-in RagLiveSmoke.csproj or the
authorized Python P02+P04 flow with real /api/embed, document picker, citations,
ACL, update/delete and chat STOP. Independently prove GPU QLoRA on licensed
weights and authorized dataset, checkpoint/RESUME/eval/merge; E06 serial SourceLock
then E07 same-SHA Windows EXE QA. All unproven work is HOLD, not 100%.
