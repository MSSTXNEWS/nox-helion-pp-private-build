using System.Net;
using System.Text.Json;
using NoxHelion.E05;

// Offline regression executable. Does not contact Google Docs.
foreach (var order in new[] {
    new[] { "report", "lessons", "master" }, new[] { "report", "master", "lessons" },
    new[] { "lessons", "report", "master" }, new[] { "lessons", "master", "report" },
    new[] { "master", "report", "lessons" }, new[] { "master", "lessons", "report" } })
{
    foreach (bool allowMaster in new[] { false, true })
    {
        using var handler = new DocsHandler();
        using var http = new HttpClient(handler);
        var writer = new GoogleDocsAppendReadback(http, _ => Task.FromResult("fixture"));
        var targets = order.Select(x => new E05DriveTarget(x, "Doc_" + x)).ToArray();
        var result = await E05DriveRunGate.AppendRunAsync(writer, "B4-ORDER",
            "B4-ORDER report and lesson", targets, allowMaster, CancellationToken.None);
        var expected = allowMaster ? new[] { "Doc_report", "Doc_lessons", "Doc_master" }
                                   : new[] { "Doc_report", "Doc_lessons" };
        if (!handler.Writes.SequenceEqual(expected) ||
            !result.Receipts.Select(x => x.DocumentId).SequenceEqual(expected) ||
            result.State != (allowMaster ? "PASS" : "HOLD_MASTER_INTEGRITY"))
            throw new Exception("Order regression: " + string.Join(",", order));
    }
}
Console.WriteLine("PASS: all 6 permutations, master allowed/held (12 scenarios)");

sealed class DocsHandler : HttpMessageHandler
{
    public List<string> Writes { get; } = new();
    private readonly Dictionary<string, string> bodies = new();
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,
        CancellationToken ct)
    {
        var id = request.RequestUri!.AbsolutePath.Split('/')[3].Split(':')[0];
        if (request.Method == HttpMethod.Post)
        {
            using var payload = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
            bodies[id] = payload.RootElement.GetProperty("requests")[0]
                .GetProperty("insertText").GetProperty("text").GetString()!;
            Writes.Add(id);
            return Reply("{}");
        }
        bool found = bodies.TryGetValue(id, out var text);
        return Reply(JsonSerializer.Serialize(new {
            revisionId = found ? "after" : "before",
            body = new { content = new[] { new { paragraph = new { elements = new[] {
                new { textRun = new { content = text ?? "" } }
            } } } } }
        }));
    }
    private static HttpResponseMessage Reply(string json) =>
        new(HttpStatusCode.OK) { Content = new StringContent(json) };
}

