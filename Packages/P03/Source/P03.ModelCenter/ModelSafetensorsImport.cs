using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Nox.P03;

// This object is built from the authenticated P04 native result, never deserialized
// from browser payloads. P04 verifies dataset rights before granting this approval.
public sealed record P04MergedImportApproval(string Directory, string MergedPayloadSha256,
    string MergeReceiptSha256, string TrainingReceiptPath, string TrainingReceiptSha256,
    string RightsAttestationId, string RightsAttestationSha256, string LicenseSource,
    string NativeApprovalId, bool NativeRightsVerified);
public sealed record ImportedModelFile(string Path, string Sha256, long SizeBytes);

public sealed class SafetensorsImportHold(string code) : IOException(code)
{
    public string Code { get; } = code;
}

internal static class ModelSafetensorsImport
{
    private static readonly Regex Sha=new("^[a-f0-9]{64}$");
    private static readonly Regex Name=new("^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$");
    private const long MaxTotal=1L<<40;
    internal static async Task<IReadOnlyList<ImportedModelFile>> ValidateAsync(
        P04MergedImportApproval approval,CancellationToken ct)
    {
        if (!approval.NativeRightsVerified || string.IsNullOrWhiteSpace(approval.NativeApprovalId) ||
            approval.NativeApprovalId.Length>200 || string.IsNullOrWhiteSpace(approval.RightsAttestationId) ||
            !new[]{approval.MergedPayloadSha256,approval.MergeReceiptSha256,
                approval.TrainingReceiptSha256,approval.RightsAttestationSha256}.All(x=>Sha.IsMatch(x??"")) ||
            !Uri.TryCreate(approval.LicenseSource,UriKind.Absolute,out var license) ||
            license.Scheme!=Uri.UriSchemeHttps || !string.IsNullOrEmpty(license.UserInfo))
            throw new InvalidDataException("P03_P04_NATIVE_RIGHTS_APPROVAL_REQUIRED");
        ModelLocalAttestation.RequireNoExistingReparsePoint(approval.Directory);
        if (!System.IO.Directory.Exists(approval.Directory))
            throw new InvalidDataException("P03_MERGED_DIRECTORY_MISSING");
        using var merge=await ReadPinnedJsonAsync(System.IO.Path.Combine(approval.Directory,"merge-receipt.json"),approval.MergeReceiptSha256,ct);
        using var training=await ReadPinnedJsonAsync(approval.TrainingReceiptPath,approval.TrainingReceiptSha256,ct);
        var m=merge.RootElement;var t=training.RootElement;
        if (m.GetProperty("schema").GetString()!="NOX-QLORA-MERGE-RECEIPT-v1" || m.GetProperty("status").GetString()!="CREATED" ||
            m.GetProperty("merged_payload_sha256").GetString()!=approval.MergedPayloadSha256 ||
            m.GetProperty("training_receipt_sha256").GetString()!=approval.TrainingReceiptSha256 ||
            t.GetProperty("schema").GetString()!="NOX-QLORA-TRAINING-RECEIPT-v2" || t.GetProperty("status").GetString()!="COMPLETED" ||
            t.GetProperty("dataset").GetProperty("rights_attestation_id").GetString()!=approval.RightsAttestationId ||
            t.GetProperty("dataset").GetProperty("rights_attestation_sha256").GetString()!=approval.RightsAttestationSha256 ||
            t.GetProperty("training").GetProperty("evaluation_status").GetString()!="VALID" ||
            t.GetProperty("adapter_sha256").GetString()!=m.GetProperty("adapter_sha256").GetString())
            throw new InvalidDataException("P03_P04_MERGE_EVIDENCE_MISMATCH");
        var model=t.GetProperty("model");var dataset=t.GetProperty("dataset");
        if (model.GetProperty("id").GetString()!=m.GetProperty("model_id").GetString() ||
            model.GetProperty("revision").GetString()!=m.GetProperty("model_revision").GetString() ||
            model.GetProperty("snapshot_sha256").GetString()!=m.GetProperty("model_snapshot_sha256").GetString() ||
            string.IsNullOrWhiteSpace(dataset.GetProperty("owner_approval_id").GetString()) ||
            string.IsNullOrWhiteSpace(dataset.GetProperty("license_id").GetString()) ||
            !Sha.IsMatch(dataset.GetProperty("train_sha256").GetString()??"") ||
            !Sha.IsMatch(dataset.GetProperty("holdout_sha256").GetString()??"") ||
            dataset.GetProperty("train_sha256").GetString()==dataset.GetProperty("holdout_sha256").GetString())
            throw new InvalidDataException("P03_P04_BASE_RIGHTS_HOLDOUT_MISMATCH");
        var baseline=t.GetProperty("training").GetProperty("baseline_eval_loss").GetDouble();
        var trained=t.GetProperty("training").GetProperty("adapter_eval_loss").GetDouble();
        if (!double.IsFinite(baseline) || !double.IsFinite(trained) || baseline<0 || trained<0 || trained>=baseline ||
            m.GetProperty("baseline_eval_loss").GetDouble()!=baseline || m.GetProperty("adapter_eval_loss").GetDouble()!=trained)
            throw new InvalidDataException("P03_P04_EVALUATION_HOLD");
        var entries=System.IO.Directory.GetFileSystemEntries(approval.Directory);
        if (entries.Length is < 4 or > 257)throw new InvalidDataException("P03_MERGED_FILE_COUNT_HOLD");
        var files=new List<ImportedModelFile>();long total=0;
        foreach(var path in entries.OrderBy(System.IO.Path.GetFileName,StringComparer.Ordinal))
        {
            ct.ThrowIfCancellationRequested();var name=System.IO.Path.GetFileName(path);
            ModelLocalAttestation.RequireRegularUnlinkedFile(path);
            if (name=="merge-receipt.json")continue;
            if (!Name.IsMatch(name) || !(name.EndsWith(".safetensors",StringComparison.Ordinal) ||
                name.EndsWith(".json",StringComparison.Ordinal) || name.EndsWith(".model",StringComparison.Ordinal) ||
                name.EndsWith(".txt",StringComparison.Ordinal) || name.EndsWith(".jinja",StringComparison.Ordinal)))
                throw new InvalidDataException("P03_MERGED_FILE_TYPE_HOLD");
            await using var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read,1<<20,true);
            if (stream.Length is <=0 or > (1L<<38))throw new InvalidDataException("P03_MERGED_FILE_SIZE_HOLD");
            total=checked(total+stream.Length);if(total>MaxTotal)throw new InvalidDataException("P03_MERGED_TOTAL_SIZE_HOLD");
            if(name.EndsWith(".safetensors",StringComparison.Ordinal))await CheckSafetensorsAsync(stream,ct);
            stream.Position=0;var hash=Convert.ToHexString(await SHA256.HashDataAsync(stream,ct)).ToLowerInvariant();
            files.Add(new(name,hash,stream.Length));
        }
        if (!files.Any(x=>x.Path=="config.json") || !files.Any(x=>x.Path.EndsWith(".safetensors",StringComparison.Ordinal)) ||
            !files.Any(x=>x.Path is "tokenizer.json" or "tokenizer.model"))
            throw new InvalidDataException("P03_MERGED_MODEL_CONFIG_TOKENIZER_REQUIRED");
        using var tree=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach(var file in files)
        {
            var name=Encoding.UTF8.GetBytes(file.Path);var length=new byte[4];
            BinaryPrimitives.WriteUInt32BigEndian(length,checked((uint)name.Length));
            tree.AppendData(length);tree.AppendData(name);tree.AppendData(Convert.FromHexString(file.Sha256));
        }
        if (Convert.ToHexString(tree.GetHashAndReset()).ToLowerInvariant()!=approval.MergedPayloadSha256)
            throw new InvalidDataException("P03_MERGED_PAYLOAD_SHA_MISMATCH");
        return files.AsReadOnly();
    }

    private static async Task<JsonDocument> ReadPinnedJsonAsync(string path,string expected,CancellationToken ct)
    {
        ModelLocalAttestation.RequireRegularUnlinkedFile(path);
        await using var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read,8192,true);
        if(file.Length is <2 or > 1048576)throw new InvalidDataException("P03_P04_RECEIPT_SIZE_HOLD");
        using var memory=new MemoryStream();await file.CopyToAsync(memory,ct);var bytes=memory.ToArray();
        if(Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()!=expected)
            throw new InvalidDataException("P03_P04_RECEIPT_SHA_MISMATCH");
        return JsonDocument.Parse(bytes,new JsonDocumentOptions { MaxDepth=32 });
    }

    private static async Task CheckSafetensorsAsync(FileStream file,CancellationToken ct)
    {
        var header=new byte[8];await file.ReadExactlyAsync(header,ct);
        var size=BinaryPrimitives.ReadUInt64LittleEndian(header);
        if(size is <2 or > 16777216 || size>(ulong)Math.Max(0,file.Length-8))
            throw new InvalidDataException("P03_SAFETENSORS_HEADER_INVALID");
        var bytes=new byte[checked((int)size)];await file.ReadExactlyAsync(bytes,ct);
        using var doc=JsonDocument.Parse(bytes,new JsonDocumentOptions {MaxDepth=16});
        if(doc.RootElement.ValueKind!=JsonValueKind.Object)throw new InvalidDataException("P03_SAFETENSORS_HEADER_INVALID");
        var tensors=0;
        foreach(var tensor in doc.RootElement.EnumerateObject())
        {
            if(tensor.Name=="__metadata__")continue;
            var offsets=tensor.Value.GetProperty("data_offsets");
            if(offsets.ValueKind!=JsonValueKind.Array || offsets.GetArrayLength()!=2 ||
                !offsets[0].TryGetInt64(out var start) || !offsets[1].TryGetInt64(out var end) ||
                start<0 || end<start || end>file.Length-8-(long)size)
                throw new InvalidDataException("P03_SAFETENSORS_OFFSETS_INVALID");
            tensors++;
        }
        if(tensors==0)throw new InvalidDataException("P03_SAFETENSORS_NO_TENSORS");
    }
}
