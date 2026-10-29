using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.E05;

public static class E05FinishChecks
{
    public static async Task RunAsync()
    {
        static void Verify(bool success, string name)
        {
            if (!success) throw new Exception("E05 FINISH: " + name);
            Console.WriteLine("PASS FINISH " + name);
        }
        var now = DateTimeOffset.UtcNow;
        var offline = E05HostStateAdapter.Capture("E05-FINISH-RUN", now,
            Array.Empty<ISensorProvider>(), null, null,
            null, null, "HOLD", "NOT_RUN", CancellationToken.None);
        Verify(offline.Readiness.Bars.Count == 7 && offline.Readiness.Overall is null &&
            offline.Space.ProductProgress is null && offline.Space.Access == "READ_ONLY",
            "missing frozen receipts never create release percentages");
        Verify(offline.Hardware.RunId == offline.Space.RunId &&
            offline.Hardware.State == "UNAVAILABLE",
            "one native RunID for unavailable sensors and NOX SPACE");
        var positive = new FixtureVerifier();
        var lanes = Enumerable.Range(1, 5).Select(i => new E05SealedLane(
            i, new string('a', 64), new[] {
                new E05SealedCriterion("T" + i, 1m, "ACCEPTED", "owner-fixture",
                    new string('b', 64))
            })).ToArray();
        var backed = E05HostStateAdapter.Capture("E05-FINISH-RUN", now,
            Array.Empty<ISensorProvider>(), lanes, positive,
            null, null, "HOLD", "NOT_RUN", CancellationToken.None);
        Verify(backed.Readiness.Overall == 100m &&
            backed.Space.ProductProgress == 100m &&
            backed.Readiness.Bars[5].Percent is null &&
            backed.Readiness.Bars[6].Percent is null,
            "only independent receipt verifier can supply numerical demo percentage");
        var bad = E05HostStateAdapter.Capture("E05-FINISH-RUN", now,
            Array.Empty<ISensorProvider>(), lanes, null, null, null,
            "PASS", "PASS", CancellationToken.None);
        Verify(bad.Space.ProductProgress is null,
            "even claimed host gates cannot fabricate missing receipt percentages");
        var approved = new ApprovedFeed("weather", "fixture",
            new Uri("https://example.org/weather"), "example.org",
            "licence-fixture", TimeSpan.FromMinutes(10),
            TimeSpan.FromSeconds(3), TimeSpan.FromHours(1));
        var dated = new FeedResult("weather", "fixture", "{}",
            now.AddMinutes(-2), now.AddMinutes(-1), "LIVE", null, false);
        var sourceView = E05HostStateAdapter.Capture("E05-FINISH-RUN", now,
            Array.Empty<ISensorProvider>(), null, null,
            new[] { dated }, new Dictionary<string, ApprovedFeed> {
                ["weather"] = approved }, "HOLD", "NOT_RUN", CancellationToken.None);
        Verify(sourceView.Space.Tiles.Single().Status == "SOURCE_DATED",
            "approved dated source preserved without invented weather values");
        var denied = E05HostStateAdapter.Capture("E05-FINISH-RUN", now,
            Array.Empty<ISensorProvider>(), null, null, new[] { dated }, null,
            "HOLD", "NOT_RUN", CancellationToken.None);
        Verify(denied.Space.Tiles.Single().Status == "DISABLED",
            "no licensed source means disabled feed");
        using var http = new HttpClient(new DocsMockHandler());
        var writer = new GoogleDocsAppendReadback(http,
            _ => Task.FromResult("fixture-token"));
        var targets = new[] {
            new E05DriveTarget("report", "1TestReportDoc"),
            new E05DriveTarget("lessons", "1TestLessonsDoc")
        };
        var accepted = await E05SafeRunReports.AppendAsync(writer,
            "E05-FINISH-RUN", "E05-FINISH-RUN report fixture",
            "E05-FINISH-RUN lesson fixture", targets, CancellationToken.None);
        Verify(accepted.State == "REPORT_LESSONS_PASS_MASTER_HOLD" &&
            accepted.Receipts.Count == 2 &&
            accepted.Receipts.All(r => r.Status == "READBACK_PASS"),
            "Google Docs report and lesson mock readback without master write");
        var unsafeTargets = targets.Concat(new[] {
            new E05DriveTarget("master", "1UnverifiedMaster") }).ToArray();
        var refused = await E05SafeRunReports.AppendAsync(writer,
            "E05-FINISH-RUN", "E05-FINISH-RUN report",
            "E05-FINISH-RUN lesson", unsafeTargets, CancellationToken.None);
        Verify(refused.State == "HOLD_CONTRACT" && refused.Receipts.Count == 0,
            "master target rejected before any report write");
    }
    private sealed class FixtureVerifier : IE05ReceiptVerifier
    {
        public bool IsFrozenManifest(string sha, int lane) =>
            sha == new string('a',64) && lane is >= 1 and <= 5;
        public bool IsVerified(string task, string receipt, string hash) =>
            task.StartsWith("T", StringComparison.Ordinal) &&
            receipt == "owner-fixture" && hash == new string('b',64);
    }
    private sealed class DocsMockHandler : HttpMessageHandler
    {
        private readonly Dictionary<string,string> content = new();
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken ct)
        {
            var id = request.RequestUri!.AbsolutePath.Split('/')[3].Split(':')[0];
            if (request.Method == HttpMethod.Post)
            {
                var body = request.Content!.ReadAsStringAsync(ct).GetAwaiter().GetResult();
                using var doc = System.Text.Json.JsonDocument.Parse(body);
                content[id] = doc.RootElement.GetProperty("requests")[0]
                    .GetProperty("insertText").GetProperty("text").GetString()!;
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
                    Content = new StringContent("{}")
                });
            }
            content.TryGetValue(id, out var existing);
            var text = System.Text.Json.JsonSerializer.Serialize(new {
                revisionId = existing is null ? "rev1" : "rev2",
                body = new { content = new[] {
                    new { paragraph = new { elements = new[] {
                        new { textRun = new { content = existing ?? "" } }
                    } } }
                } }
            });
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
                Content = new StringContent(text)
            });
        }
    }
}
