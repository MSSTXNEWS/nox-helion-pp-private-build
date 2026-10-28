# E07 R10 · P04 C# RAG JSON owner/citation parity — SOURCE RED

TaskID: `E07-SRC-P04-CSHARP-DUPLICATE-INDEX-PROVENANCE-01`  
RunID: `NOX-V16-E07-M2-20261028-R10`  
Pinned PR162 preimage: `eebb89df8c280ae15d388514f1d0ec15fa80fc50`  
Existing owner C# source Git blob: `35dcaffad780ce5b0501422a2bc406ec52e12b26`  
Existing Python RAG Git blob: `58af025bd05f0e99a445b56c307e12d600b8f19f`

No product code changed. This QA-only project references existing `Packages/P04/NoxP04.csproj`, with a real local disk index. It requests a SID/conversation that does not own any sources: **no Ollama/network request** is needed. Cases: valid empty index; duplicate schema; case-insensitive schema alias; duplicate sources; duplicate ownerSid of an unrelated owner; duplicate chunkSha256 in an unrelated owner source.

Expected current behavior: first test succeeds, subsequent duplicate-key tests should FAIL (negative RED). Passing status is reserved for future existing-owner C# fix. **Do not count a RED run as product QA pass.**

To run on .NET8 SDK:
```powershell
dotnet run --project qa/e07/P04NativeIndexDuplicateR10/P04NativeIndexDuplicateR10.csproj
```

Owner #1 narrow fix: reject duplicate JSON object keys **at every nesting level** and case-insensitively (RagService uses `JsonSerializerDefaults.Web`), before `JsonSerializer.Deserialize`. Preserve old index layout, the 256 MiB limit, file lock, atomic writes, SID/scope/citation checks, and all Python compatibility. Avoid `JsonSerializerOptions.AllowDuplicateProperties` on net8; it was added in .NET10. Do not create another index, RAG worker or database.

Full native .NET8 execution and independent Windows E07 are NOT_RUN in the current QA runtime because no dotnet SDK / installed NOX binary is available. This is only the source regression and owner handoff. Release HOLD until 10 real Windows E2E on one frozen BuildID/SHA.
