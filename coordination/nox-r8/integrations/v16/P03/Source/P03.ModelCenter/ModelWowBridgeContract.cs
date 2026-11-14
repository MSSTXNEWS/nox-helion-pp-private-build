using System.Text.Json;
using Nox.P03;

namespace Nox.P03.Wow;

/// <summary>
/// Host-neutral WebView2 message serializer/validator. Owner #6 alone wires this
/// to the approved WebView2 instance after validating WebMessageReceived.Source.
/// No WebView2 package reference, new queue, or background service is required.
/// </summary>
public static class ModelWowBridgeContract
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private const double GiB = 1073741824d;

    public sealed record DeviceSnapshot(double? VramFreeGiB, double? RamFreeGiB, double? DiskFreeGiB);
    public sealed record Capabilities(bool Stop = false, bool Retry = false, bool Diagnose = false,
        bool Pull = false, bool ImportGguf = false);
    public sealed record Command(string CommandId, string Action, Guid? JobId, string? ModelId);

    public static string SnapshotJson(IEnumerable<ModelCatalogEntry> entries,
        IEnumerable<ModelJob> jobs, Guid? activeJobId = null,
        DeviceSnapshot? hardware = null, Capabilities? capabilities = null)
    {
        ArgumentNullException.ThrowIfNull(entries);
        ArgumentNullException.ThrowIfNull(jobs);
        var catalog = entries.ToArray();
        if (catalog.Length is < 1 or > 250 || catalog.Any(m => m is null || string.IsNullOrWhiteSpace(m.Id)) ||
            catalog.Select(m => m.Id).Distinct(StringComparer.Ordinal).Count()!=catalog.Length)
            throw new InvalidDataException("P03_SNAPSHOT_DUPLICATE_OR_INVALID_MODEL");
        var activeMatches=activeJobId.HasValue?jobs.Where(x=>x.Id==activeJobId.Value).Take(2).ToArray():Array.Empty<ModelJob>();
        if(activeMatches.Length>1)throw new InvalidDataException("P03_SNAPSHOT_AMBIGUOUS_JOB");
        var job=activeMatches.FirstOrDefault();
        var matched = job is null ? null : catalog.FirstOrDefault(x =>
            string.Equals(x.ExactTag, job.ModelTag, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(x.Id, job.ModelTag, StringComparison.OrdinalIgnoreCase));
        // Only properties grounded in the catalog and the actual queue are included.
        return JsonSerializer.Serialize(new
        {
            type = "p03.snapshot.v1",
            models = catalog.Select(m => new
            {
                m.Id, m.Name, officialUrl = m.OfficialLibraryPage.ToString(),
                artifactVerified = m.CanOfferOneClickPull,
                exactTag = m.ExactTag, immutableRevision = m.ImmutableRevision,
                m.License, licenseEvidenceUrl = m.LicenseEvidenceUri?.ToString(),
                artifactBytes = m.ArtifactBytes,
                sha256 = m.ExpectedSha256, manifestSha256 = m.ExpectedManifestDigestSha256,
                compatibilityReviewed = m.CompatibilityReviewed,
                requiredDiskGiB = m.RequiredDiskBytes is > 0 ? m.RequiredDiskBytes.Value / GiB : (double?)null,
                requiredVramGiB = m.RecommendedVramBytes is > 0 ? m.RecommendedVramBytes.Value / GiB : (double?)null,
                recommendedRamGiB = m.RecommendedRamBytes is > 0 ? m.RecommendedRamBytes.Value / GiB : (double?)null
            }),
            activeJob = job is null ? null : new
            {
                jobId = job.Id.ToString("D"), modelId = matched?.Id,
                modelTag = job.ModelTag, state = job.State.ToString(),
                status = job.Status, completedBytes = job.CompletedBytes,
                totalBytes = job.TotalBytes
            },
            hardware,
            capabilities = capabilities ?? new Capabilities(),
            quickActions = ModelQuickActions.OllamaSlots.Select(s => new { s.Id, s.DisplayName, s.Role, approved = catalog.Any(m => m.Id == s.Id && m.CanOfferOneClickPull) }),
            externalLeads = ModelQuickActions.ExternalLeads.Select(s=>new { s.Id, s.DisplayName, s.Role, officialUrl=s.ProjectPage.ToString(), s.Status, s.DownloadAllowed })
        }, JsonOptions);
    }

    public static string EventJson(ModelLifecycleEvent item)
    {
        ArgumentNullException.ThrowIfNull(item);
        return JsonSerializer.Serialize(new
        {
            type = "p03.event.v1",
            @event = new
            {
                jobId = item.JobId.ToString("D"), item.ModelTag,
                item.Phase, item.Status, item.CompletedBytes, item.TotalBytes,
                item.Digest, item.Error, atUtc = item.AtUtc
            }
        }, JsonOptions);
    }

    /// <summary>ACK echoes exact command identity, never an installation receipt.</summary>
    public static string AckJson(Command cmd,bool accepted,string? reason=null)
    {
        ArgumentNullException.ThrowIfNull(cmd);
        if(string.IsNullOrWhiteSpace(cmd.CommandId)||cmd.CommandId.Length>64||
           cmd.CommandId.Any(ch=>!char.IsAsciiLetterOrDigit(ch)&&ch!='-'&&ch!='_')||
           cmd.Action is not ("pull" or "importGguf" or "stop" or "retry" or "diagnose"))
            throw new ArgumentException("Invalid command identity",nameof(cmd));
        var safe=reason is null?"HOST_DENIED":new string(reason.Where(ch=>!char.IsControl(ch)).Take(160).ToArray());
        return JsonSerializer.Serialize(new{type="p03.command.ack.v1",commandId=cmd.CommandId,action=cmd.Action,
            accepted,reason=accepted?null:safe},JsonOptions);
    }

    /// <summary>Validate bounded command shape and current queue state.
    /// The host must also validate trusted document origin, user authorization,
    /// per-job ACL, and capability before calling the worker; success ACK is not completion.
    /// </summary>
    public static bool TryParseCommand(string payload, IReadOnlyCollection<ModelJob> jobs,
        Capabilities allowed, out Command? command) =>
        TryParseCommand(payload, jobs, [], allowed, out command);

    public static bool TryParseCommand(string payload, IReadOnlyCollection<ModelJob> jobs,
        IReadOnlyCollection<ModelCatalogEntry> approvedCatalog,
        Capabilities allowed, out Command? command)
    {
        command = null;
        if (string.IsNullOrWhiteSpace(payload) || payload.Length > 2048 || jobs is null || approvedCatalog is null || allowed is null)
            return false;
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("type", out var type) || type.GetString() != "p03.command.v1" ||
                !root.TryGetProperty("action", out var actionProp) || actionProp.ValueKind != JsonValueKind.String ||
                !root.TryGetProperty("commandId", out var idProp) || idProp.ValueKind != JsonValueKind.String)
                return false;
            var seen=new HashSet<string>(StringComparer.Ordinal);
            foreach(var field in root.EnumerateObject())
                if(!seen.Add(field.Name)||field.Name is not ("type" or "action" or "commandId" or "modelId" or "jobId" or "licenseAcknowledged"))
                    return false;
            string? action = actionProp.GetString();
            string? id = idProp.GetString();
            if (string.IsNullOrWhiteSpace(id) || id.Length > 64 ||
                id.Any(c => !char.IsAsciiLetterOrDigit(c) && c != '-' && c != '_')) return false;
            if (action == "pull" && allowed.Pull)
            {
                if (!root.TryGetProperty("modelId", out var selected) || selected.ValueKind != JsonValueKind.String ||
                    !root.TryGetProperty("licenseAcknowledged", out var ack) || ack.ValueKind != JsonValueKind.True)
                    return false;
                var matches = approvedCatalog.Where(x => x.Id == selected.GetString()).Take(2).ToArray();
                if (matches.Length != 1 || !matches[0].CanOfferOneClickPull) return false;
                command = new Command(id, action, null, matches[0].Id);
                return true;
            }
            if (action == "importGguf" && allowed.ImportGguf)
            {
                if (!root.TryGetProperty("licenseAcknowledged", out var ack) || ack.ValueKind != JsonValueKind.True) return false;
                // File picker, rights approval, SHA and ACL must be hosted natively by #6.
                // Never accept untrusted JS paths, blobs or checksum claims.
                command = new Command(id, action, null, null);
                return true;
            }
            if (action == "diagnose" && allowed.Diagnose)
            {
                command = new Command(id, action, null, null);
                return true;
            }
            if ((action != "stop" || !allowed.Stop) && (action != "retry" || !allowed.Retry)) return false;
            if (!root.TryGetProperty("jobId", out var jobProp) || jobProp.ValueKind != JsonValueKind.String ||
                !Guid.TryParse(jobProp.GetString(), out var jobId)) return false;
            var jobMatches=jobs.Where(x=>x.Id==jobId).Take(2).ToArray();
            if(jobMatches.Length!=1)return false;
            var job=jobMatches[0];
            if (action == "stop" && job.State is not (ModelJobState.Queued or ModelJobState.Running)) return false;
            if (action == "retry" && job.State is not (ModelJobState.Failed or ModelJobState.Cancelled))
                return false;
            command = new Command(id, action!, jobId, null);
            return true;
        }
        catch (JsonException) { return false; }
        catch (InvalidOperationException) { return false; }
    }
}