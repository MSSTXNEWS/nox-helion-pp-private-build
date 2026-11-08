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
        if (writer is null || string.IsNullOrWhiteSpace(runId) ||
            string.IsNullOrWhiteSpace(report) || string.IsNullOrWhiteSpace(lesson) ||
            !report.Contains(runId, StringComparison.Ordinal) ||
            !lesson.Contains(runId, StringComparison.Ordinal) ||
            targets is null || targets.Count != 2 ||
            targets.Any(x => x is null || string.IsNullOrWhiteSpace(x.DocumentId)) ||
            targets.Count(x => x.Purpose == "report") != 1 ||
            targets.Count(x => x.Purpose == "lessons") != 1 ||
            targets[0].DocumentId == targets[1].DocumentId)
            return new(runId ?? "", "HOLD_CONTRACT", Array.Empty<DriveAppendReceipt>());
        var receipts = new List<DriveAppendReceipt>();
        foreach (string purpose in new[] { "report", "lessons" })
        {
            ct.ThrowIfCancellationRequested();
            var t = targets.Single(x => x.Purpose == purpose);
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
