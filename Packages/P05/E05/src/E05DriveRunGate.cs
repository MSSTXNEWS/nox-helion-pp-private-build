using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

public sealed record E05DriveTarget(string Purpose, string DocumentId);
public sealed record E05DriveRunGateResult(string RunId, string State,
    IReadOnlyList<DriveAppendReceipt> Receipts);

public static class E05DriveRunGate
{
    // App-side E06 report / separate lessons / master. Requires host OAuth,
    // explicit document allowlist, and independent readback for every target.
    // The host can disable master writes if historical integrity is unverified.
    public static async Task<E05DriveRunGateResult> AppendRunAsync(
        GoogleDocsAppendReadback writer, string runId, string text,
        IReadOnlyList<E05DriveTarget> approved, bool masterIntegrityVerified,
        CancellationToken stop)
    {
        var snapshot = approved?.ToArray();
        if (writer is null || string.IsNullOrWhiteSpace(runId) ||
            string.IsNullOrWhiteSpace(text) ||
            !text.Contains(runId, StringComparison.Ordinal) ||
            snapshot is null || snapshot.Length != 3 ||
            snapshot.Any(x => x is null || !GoogleDocsAppendReadback.ValidInput(x.DocumentId, runId, text)) ||
            snapshot.Select(x => x.DocumentId).Distinct(StringComparer.Ordinal).Count() != 3 ||
            !new[] { "report", "lessons", "master" }.All(p =>
                snapshot.Count(t => t.Purpose == p) == 1))
            return new(runId, "HOLD_CONTRACT", Array.Empty<DriveAppendReceipt>());
        var receipts = new List<DriveAppendReceipt>();
        // Persist the report and lesson before evaluating the optional master gate.
        // Caller ordering must not prevent their independent readback receipts.
        foreach (string purpose in new[] { "report", "lessons", "master" })
        {
            var target = snapshot.Single(x => x.Purpose == purpose);
            stop.ThrowIfCancellationRequested();
            if (target.Purpose == "master" && !masterIntegrityVerified)
                return new(runId, "HOLD_MASTER_INTEGRITY", receipts);
            DriveAppendReceipt receipt;
            try { receipt = await writer.AppendAsync(target.DocumentId, runId,
                    text, stop).ConfigureAwait(false); }
            catch (OperationCanceledException) when (stop.IsCancellationRequested) { throw; }
            catch (Exception) { return new(runId, "HOLD_WRITE_OR_READBACK", receipts); }
            receipts.Add(receipt);
            // Confirm the returned receipt belongs to this run and document.
            if (receipt.RunId != runId || receipt.DocumentId != target.DocumentId ||
                receipt.ExpectedChars != text.Length ||
                receipt.Status is not ("READBACK_PASS" or "ALREADY_PRESENT") ||
                string.IsNullOrWhiteSpace(receipt.RevisionAfter))
                return new(runId, "HOLD_WRITE_OR_READBACK", receipts);
        }
        return new(runId, "PASS", receipts);
    }
}

