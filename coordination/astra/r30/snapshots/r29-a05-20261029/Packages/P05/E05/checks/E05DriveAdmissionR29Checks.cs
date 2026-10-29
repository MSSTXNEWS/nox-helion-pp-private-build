using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.E05;

// Offline HTTP fixtures against the actual production writer. No OAuth/network.
public static class E05DriveAdmissionR29Checks
{
    private const string Run = "R29-A05-DOCS";
    private const string Entry = Run + " evidence\n";
    private static void Check(bool ok, string name)
    { if (!ok) throw new Exception("R29 Drive: " + name); Console.WriteLine("PASS R29 Drive " + name); }
    private static object Body(string text) => new { content = new[] {
        new { paragraph = new { elements = new[] { new { textRun = new { content = text } } } } }
    } };
    private static object Tab(string id, string text) => new {
        tabProperties = new { tabId = id }, documentTab = new { body = Body(text) }
    };
    private static string Doc(string? revision, params object[] tabs) =>
        JsonSerializer.Serialize(new { revisionId = revision, tabs });
    private static HttpResponseMessage Json(string text, HttpStatusCode status = HttpStatusCode.OK) =>
        new(status) { Content = new StringContent(text) };

    public static async Task RunAsync()
    {
        async Task CheckTabs(string name, string before, string after, string expected)
        {
            using var handler = new ScriptedHandler(new[] {
                (HttpMethod.Get, before, HttpStatusCode.OK),
                (HttpMethod.Post, "{}", HttpStatusCode.OK),
                (HttpMethod.Get, after, HttpStatusCode.OK)
            });
            handler.CheckPost = root => {
                Check(root.GetProperty("writeControl").GetProperty("requiredRevisionId").GetString() == "rev1",
                    name + " retains exact CAS revision");
                Check(root.GetProperty("requests")[0].GetProperty("insertText")
                    .GetProperty("endOfSegmentLocation").GetProperty("tabId").GetString() == "tab-A",
                    name + " pins selected tab");
            };
            using var http = new HttpClient(handler);
            var result = await new GoogleDocsAppendReadback(http, _ => Task.FromResult("fixture"))
                .AppendAsync("Document1", Run, Entry, CancellationToken.None);
            Check(result.Status == expected && handler.Posts == 1 && handler.Remaining == 0, name);
        }
        await CheckTabs("other tab cannot falsely satisfy idempotence",
            Doc("rev1", Tab("tab-A", ""), Tab("tab-B", Entry)),
            Doc("rev2", Tab("tab-A", Entry), Tab("tab-B", Entry)), "READBACK_PASS");
        await CheckTabs("cross-tab fragments cannot manufacture an entry",
            Doc("rev1", Tab("tab-A", Entry[..5]), Tab("tab-B", Entry[5..])),
            Doc("rev2", Tab("tab-A", Entry), Tab("tab-B", Entry[5..])), "READBACK_PASS");
        await CheckTabs("entry in other tab is not target readback",
            Doc("rev1", Tab("tab-A", ""), Tab("tab-B", "")),
            Doc("rev2", Tab("tab-A", ""), Tab("tab-B", Entry)), "READBACK_MISMATCH");
        await CheckTabs("tab reorder preserves original destination identity",
            Doc("rev1", Tab("tab-A", ""), Tab("tab-B", "")),
            Doc("rev2", Tab("tab-B", ""), Tab("tab-A", Entry)), "READBACK_PASS");
        await CheckTabs("missing destination fails closed",
            Doc("rev1", Tab("tab-A", "")), Doc("rev2", Tab("tab-B", Entry)), "READBACK_TAB_MISSING");
        await CheckTabs("missing readback revision is not PASS",
            Doc("rev1", Tab("tab-A", "")), Doc(null, Tab("tab-A", Entry)), "NO_READBACK_REVISION");

        using (var handler = new ScriptedHandler(new[] {
            (HttpMethod.Get, JsonSerializer.Serialize(new { revisionId = "rev1", body = Body("") }), HttpStatusCode.OK),
            (HttpMethod.Post, "{}", HttpStatusCode.OK),
            (HttpMethod.Get, Doc("rev2", Tab("new-tab", Entry)), HttpStatusCode.OK)
        }))
        {
            using var http = new HttpClient(handler);
            var result = await new GoogleDocsAppendReadback(http, _ => Task.FromResult("fixture"))
                .AppendAsync("Document1", Run, Entry, CancellationToken.None);
            Check(result.Status == "READBACK_TAB_MISSING" && handler.Remaining == 0,
                "legacy-to-tabs transition cannot invent original destination identity");
        }

        using (var handler = new ScriptedHandler(new[] {
            (HttpMethod.Get, Doc("rev1", Tab("tab-A", "")), HttpStatusCode.OK),
            (HttpMethod.Post, "{}", HttpStatusCode.BadRequest),
            (HttpMethod.Get, Doc("rev2", Tab("tab-A", "")), HttpStatusCode.OK),
            (HttpMethod.Post, "{}", HttpStatusCode.OK),
            (HttpMethod.Get, Doc("rev3", Tab("tab-A", Entry)), HttpStatusCode.OK)
        }))
        {
            handler.CheckPost = root => Check(root.GetProperty("writeControl")
                .GetProperty("requiredRevisionId").GetString() == (handler.Posts == 1 ? "rev1" : "rev2"),
                "retry rereads current revision instead of replaying stale CAS");
            using var http = new HttpClient(handler);
            var writer = new GoogleDocsAppendReadback(http, _ => Task.FromResult("fixture"));
            var rejected = await writer.AppendAsync("Document1", Run, Entry, CancellationToken.None);
            Check(rejected.Status == "REVISION_CONFLICT_OR_REJECTED" && handler.Remaining == 3,
                "400 remains HOLD with no automatic blind retry");
            var retried = await writer.AppendAsync("Document1", Run, Entry, CancellationToken.None);
            Check(retried.Status == "READBACK_PASS" && handler.Remaining == 0,
                "explicit retry performs fresh bounded read-CAS-readback");
        }

        foreach (bool reportsOnly in new[] { false, true })
        {
            var approved = reportsOnly ? new[] {
                new E05DriveTarget("report", "Report1"), new E05DriveTarget("lessons", "Lessons1")
            } : new[] {
                new E05DriveTarget("report", "Report1"), new E05DriveTarget("lessons", "Lessons1"),
                new E05DriveTarget("master", "Master1")
            };
            using var handler = new StoredHandler();
            using var http = new HttpClient(handler);
            var writer = new GoogleDocsAppendReadback(http, _ => {
                approved[1] = new E05DriveTarget("lessons", "UnapprovedDoc");
                return Task.FromResult("fixture");
            });
            var result = reportsOnly
                ? await E05SafeRunReports.AppendAsync(writer, Run, Entry, Entry, approved, CancellationToken.None)
                : await E05DriveRunGate.AppendRunAsync(writer, Run, Entry, approved, true, CancellationToken.None);
            Check(result.Receipts.Count == (reportsOnly ? 2 : 3) &&
                handler.Writes.Contains("Lessons1") && !handler.Writes.Contains("UnapprovedDoc"),
                "allowlist snapshot survives callback mutation " + reportsOnly);
        }
        using (var http = new HttpClient(new StoredHandler()))
        {
            int tokens = 0;
            var writer = new GoogleDocsAppendReadback(http, _ => { tokens++; return Task.FromResult("fixture"); });
            foreach (var malformed in new E05DriveTarget?[] { null, new("lessons", "bad/doc") })
            {
                var result = await E05DriveRunGate.AppendRunAsync(writer, Run, Entry, new[] {
                    new E05DriveTarget("report", "Report1"), malformed!, new E05DriveTarget("master", "Master1")
                }, true, CancellationToken.None);
                Check(result.State == "HOLD_CONTRACT" && tokens == 0 && result.Receipts.Count == 0,
                    "invalid complete destination set denied before first write");
            }
        }
    }
    private sealed class ScriptedHandler : HttpMessageHandler
    {
        private readonly Queue<(HttpMethod Method, string Body, HttpStatusCode Status)> replies;
        public ScriptedHandler(IEnumerable<(HttpMethod, string, HttpStatusCode)> replies) => this.replies = new(replies);
        public int Posts { get; private set; }
        public int Remaining => replies.Count;
        public Action<JsonElement>? CheckPost { get; set; }
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var next = replies.Dequeue();
            Check(request.Method == next.Method, "HTTP operation order");
            if (request.Method == HttpMethod.Post)
            {
                Posts++;
                using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
                CheckPost?.Invoke(body.RootElement);
            }
            return Json(next.Body, next.Status);
        }
    }
    private sealed class StoredHandler : HttpMessageHandler
    {
        private readonly Dictionary<string, string> entries = new();
        public List<string> Writes { get; } = new();
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            string id = request.RequestUri!.AbsolutePath.Split('/')[3].Split(':')[0];
            if (request.Method == HttpMethod.Post)
            {
                using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
                entries[id] = body.RootElement.GetProperty("requests")[0].GetProperty("insertText").GetProperty("text").GetString()!;
                Writes.Add(id);
                return Json("{}");
            }
            bool written = entries.TryGetValue(id, out var text);
            return Json(Doc(written ? "rev2" : "rev1", Tab("tab-A", text ?? "")));
        }
    }
}
