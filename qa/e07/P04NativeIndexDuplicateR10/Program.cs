// Independent E07 SOURCE test on the existing C# P04 RagService, .NET 8.
// No network or Ollama call: requested SID/conversation has zero indexed sources.
// Expected RED on current owner blob; do not count as runtime acceptance.
using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using NoxP04.Rag;

internal static class Program
{
    static readonly string Root = """
        {"schema":"NOX-RAG-INDEX-v1","model":"fixture","vectorDimensions":0,"sources":[]}
        """;

    static async Task Check(string label, string indexJson, bool reject)
    {
        var folder = Path.Combine(Path.GetTempPath(), "NOX_RAG_QA_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var path = Path.Combine(folder, "index.json");
        var original = Encoding.UTF8.GetBytes(indexJson);
        File.WriteAllBytes(path, original);
        try {
            using var rag = new RagService(new Uri("http://127.0.0.1:11434/"), "fixture", path);
            bool failedClosed = false;
            try {
                var hits = await rag.SearchAsync("S-1-5-21-7777", "no-match", "probe");
                if (hits.Count != 0) throw new Exception("UNEXPECTED_RESULTS:" + label);
            }
            catch (InvalidDataException) { failedClosed = true; }
            catch (JsonException) { failedClosed = true; }
            if (failedClosed != reject)
                throw new Exception((reject ? "SOURCE_RED_ACCEPTED_DUPLICATES:" : "VALID_INDEX_REJECTED:") + label);
            if (!File.ReadAllBytes(path).AsSpan().SequenceEqual(original))
                throw new Exception("SOURCE_INDEX_MUTATED:" + label);
            Console.WriteLine("PASS " + label);
        } finally {
            Directory.Delete(folder, recursive: true);
        }
    }

    static async Task<int> Main()
    {
        await Check("empty-valid", Root, false);
        await Check("duplicate-schema", """
            {"schema":"NOX-RAG-INDEX-v1","schema":"NOX-RAG-INDEX-v1","model":"fixture","vectorDimensions":0,"sources":[]}
            """, true);
        await Check("schema-case-alias", """
            {"schema":"NOX-RAG-INDEX-v1","Schema":"NOX-RAG-INDEX-v1","model":"fixture","vectorDimensions":0,"sources":[]}
            """, true);
        await Check("duplicate-sources", """
            {"schema":"NOX-RAG-INDEX-v1","model":"fixture","vectorDimensions":0,"sources":[],"sources":[]}
            """, true);
        await Check("foreign-owner-duplicate", """
            {"schema":"NOX-RAG-INDEX-v1","model":"fixture","vectorDimensions":0,"sources":[{"ownerSid":"S-1-5-21-1111","ownerSid":"S-1-5-21-2222","conversationId":"foreign","sourceId":"x","chunks":[]}]}
            """, true);
        await Check("foreign-citation-duplicate", """
            {"schema":"NOX-RAG-INDEX-v1","model":"fixture","vectorDimensions":0,"sources":[{"ownerSid":"S-1-5-21-1111","conversationId":"foreign","sourceId":"x","chunks":[{"chunkIndex":0,"chunkSha256":"a","chunkSha256":"b","text":"x","vector":[1.0]}]}]}
            """, true);
        Console.WriteLine("E07_P04_NATIVE_INDEX_6_CASES_PASS");
        return 0;
    }
}
