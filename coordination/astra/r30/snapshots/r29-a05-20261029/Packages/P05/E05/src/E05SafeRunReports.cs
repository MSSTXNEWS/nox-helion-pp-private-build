using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
namespace NoxHelion.E05;
public static class E05SafeRunReports
{
    public static async Task<E05DriveRunGateResult> AppendAsync(
        GoogleDocsAppendReadback writer, string runId, string report, string lesson,
        IReadOnlyList<E05DriveTarget> targets, CancellationToken ct)
    {
        var snapshot = targets?.ToArray();
        if (writer is null || string.IsNullOrWhiteSpace(runId) ||
            string.IsNullOrWhiteSpace(report) || string.IsNullOrWhiteSpace(lesson) ||
            !report.Contains(runId, StringComparison.Ordinal) ||
            !lesson.Contains(runId, StringComparison.Ordinal) ||
            snapshot is null || snapshot.Length != 2 ||
            snapshot.Any(x => x is null || !GoogleDocsAppendReadback.ValidInput(x.DocumentId, runId,
                x.Purpose == "report" ? report : lesson)) ||
            snapshot.Count(x => x.Purpose == "report") != 1 ||
            snapshot.Count(x => x.Purpose == "lessons") != 1 ||
            snapshot[0].DocumentId == snapshot[1].DocumentId)
            return new(runId ?? "", "HOLD_CONTRACT", Array.Empty<DriveAppendReceipt>());
        var receipts = new List<DriveAppendReceipt>();
        foreach (string purpose in new[] { "report", "lessons" })
        {
            ct.ThrowIfCancellationRequested();
            var t = snapshot.Single(x => x.Purpose == purpose);
            try
            {
                var result = await writer.AppendAsync(t.DocumentId, runId,
                    purpose == "report" ? report : lesson, ct).ConfigureAwait(false);
                receipts.Add(result);
                if (result.Status is not ("READBACK_PASS" or "ALREADY_PRESENT") ||
                    string.IsNullOrWhiteSpace(result.RevisionAfter))
                    return new(runId, "HOLD_READBACK", receipts);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (Exception) { return new(runId, "HOLD_WRITE", receipts); }
        }
        return new(runId, "REPORT_LESSONS_PASS_MASTER_HOLD", receipts);
    }
}
