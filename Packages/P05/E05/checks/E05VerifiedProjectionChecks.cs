using System;
using System.Collections.Generic;
using System.Linq;
using NoxHelion.E05;

public static class E05VerifiedProjectionChecks
{
    public static void Run()
    {
        static void Check(bool ok, string name)
        {
            if (!ok) throw new Exception("Verified projection: " + name);
            Console.WriteLine("PASS " + name);
        }
        var now = DateTimeOffset.UtcNow;
        var lanes = Enumerable.Range(1, 5).Select(i => new E05SealedLane(
            i, new string('a', 64), new E05SealedCriterion[] {
                new("T" + i, 1m, "ACCEPTED", "owner-receipt", new string('b', 64))
            })).ToArray();
        var verified = E05VerifiedReadiness.Project("E05-TEST", now, lanes,
            new PositiveFixtureVerifier(), "HOLD", "NOT_RUN");
        Check(verified.Bars.Count == 7 && verified.Overall == 100m &&
            verified.Bars.Take(5).All(x => x.Percent == 100m),
            "C14 frozen five-lane owner verification computes evidenced percentages");
        Check(verified.Bars[5].Percent is null && verified.Bars[6].Percent is null,
            "C14 integration and E07 stages never earn fake percentage");
        var noVerifier = E05VerifiedReadiness.Project("E05-TEST", now, lanes,
            null, "PASS", "PASS");
        Check(noVerifier.Overall is null && noVerifier.Bars.Take(5)
            .All(x => x.Percent is null), "C14 missing verifier means N/D");
        var corrupt = lanes.ToArray();
        corrupt[0] = new E05SealedLane(1, new string('a', 64), new[] {
            new E05SealedCriterion("T1", 1m, "ACCEPTED", "owner-receipt", "invalid")
        });
        Check(E05VerifiedReadiness.Project("E05-TEST", now, corrupt,
            new PositiveFixtureVerifier(), "HOLD", "NOT_RUN").Overall is null,
            "C14 forged or malformed proof cannot yield weighted progress");

        var approvedSource = new ApprovedFeed("weather", "fixture",
            new Uri("https://example.org/weather"), "example.org", "license-verified",
            TimeSpan.FromHours(1), TimeSpan.FromSeconds(5), TimeSpan.FromHours(2));
        var known = new Dictionary<string, ApprovedFeed> { ["weather"] = approvedSource };
        var fresh = new FeedResult("weather", "fixture", "{}", now.AddMinutes(-1),
            now.AddSeconds(-5), "LIVE", null, false);
        var good = E05ApprovedSpace.Project("E05-TEST", now, new[] { fresh },
            known, null, null);
        Check(good.Tiles.Count == 1 && good.Tiles[0].Status == "SOURCE_DATED" &&
            good.ProductProgress is null && good.Access == "READ_ONLY",
            "C14 licensed source receives dated read-only status");
        var fabricatedScalar = E05ApprovedSpace.Project("E05-TEST", now,
            new[] { fresh }, known, null, 100m);
        Check(fabricatedScalar.ProductProgress is null,
            "R17 raw caller percentage cannot impersonate a sealed product ledger");
        var sealedSpace = E05ApprovedSpace.ProjectVerified("E05-TEST", now,
            new[] { fresh }, known, null, verified, lanes, new PositiveFixtureVerifier());
        Check(sealedSpace.ProductProgress == 100m,
            "R17 five independent owner seals authorize the SPACE product bar");
        var wrongRun = E05ApprovedSpace.ProjectVerified("E05-TEST", now,
            new[] { fresh }, known, null, verified with { RunId = "OTHER-RUN" },
            lanes, new PositiveFixtureVerifier());
        Check(wrongRun.ProductProgress is null,
            "R17 cross-RunID readiness rejected");
        var staleRun = E05ApprovedSpace.ProjectVerified("E05-TEST", now,
            new[] { fresh }, known, null, verified with { At = now.AddMinutes(-2) },
            lanes, new PositiveFixtureVerifier());
        Check(staleRun.ProductProgress is null,
            "R17 stale readiness rejected");
        var mismatchedOverall = E05ApprovedSpace.ProjectVerified("E05-TEST", now,
            new[] { fresh }, known, null, verified with { Overall = 50m },
            lanes, new PositiveFixtureVerifier());
        Check(mismatchedOverall.ProductProgress is null,
            "R17 changed weighted total rejected");
        var missingOwner = E05ApprovedSpace.ProjectVerified("E05-TEST", now,
            new[] { fresh }, known, null, verified, lanes, null);
        Check(missingOwner.ProductProgress is null,
            "R17 absent owner receipt verifier rejects product percentage");
        var unlicensed = E05ApprovedSpace.Project("E05-TEST", now,
            new[] { fresh }, null, null, null);
        Check(unlicensed.Tiles[0].Status == "DISABLED",
            "C14 missing source license prevents live claim");
        var expired = E05ApprovedSpace.Project("E05-TEST", now,
            new[] { fresh with { FetchedAt = now.AddHours(-2) } }, known, null, null);
        Check(expired.Tiles[0].Status == "STALE",
            "C14 expired transport cache cannot appear current");
        var wrongRunFrame = new E05HardwareFrame("OTHER-RUN", now,
            new[] { new SensorPoint("gpu.percent", 42, "%", "fixture", now, "LIVE") },
            "PARTIAL_OR_LIVE");
        Check(E05ApprovedSpace.Project("E05-TEST", now, Array.Empty<FeedResult>(),
            known, wrongRunFrame, null).Hardware.Count == 0,
            "C14 foreign RunID hardware frame denied");
    }
    private sealed class PositiveFixtureVerifier : IE05ReceiptVerifier
    {
        public bool IsFrozenManifest(string sha, int lane) =>
            sha == new string('a', 64) && lane >= 1 && lane <= 5;
        public bool IsVerified(string task, string receipt, string hash) =>
            task.StartsWith("T", StringComparison.Ordinal) &&
            receipt == "owner-receipt" && hash == new string('b', 64);
    }
}
