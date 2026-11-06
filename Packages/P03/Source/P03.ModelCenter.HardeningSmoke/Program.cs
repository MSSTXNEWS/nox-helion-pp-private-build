using System.Text;
using System.Text.Json;
using System.Runtime.InteropServices;
using Nox.P03;

int pass = 0;
void Assert(bool value, string name) { if (!value) throw new Exception("FAIL " + name); Console.WriteLine("PASS " + name); pass++; }
void MustReject(Action fn, string name) {
    try { fn(); }
    catch (InvalidDataException) { Console.WriteLine("PASS " + name); pass++; return; }
    throw new Exception("FAIL " + name);
}
// D04: run the original native header parser against real temporary files.
// This is a C# regression fixture, not installed-model proof.
var safetensorsHeaderMethod = typeof(OllamaModelAdapter).Assembly
    .GetType("Nox.P03.ModelSafetensorsImport", throwOnError: true)!
    .GetMethod("CheckSafetensorsAsync",
        System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!;
async Task<bool> AdmitHeaderD04Async(string json, int payloadBytes)
{
    var target = Path.Combine(Path.GetTempPath(),
        "nox-p03-header-" + Guid.NewGuid().ToString("N") + ".safetensors");
    var header = Encoding.UTF8.GetBytes(json);
    var content = new byte[checked(8 + header.Length + payloadBytes)];
    System.Buffers.Binary.BinaryPrimitives.WriteUInt64LittleEndian(content.AsSpan(0,8),(ulong)header.Length);
    header.CopyTo(content.AsSpan(8));
    await File.WriteAllBytesAsync(target,content);
    try
    {
        await using var file = new FileStream(target,FileMode.Open,FileAccess.Read,FileShare.Read);
        var check = (Task)safetensorsHeaderMethod.Invoke(null,new object[]{file,CancellationToken.None})!;
        try { await check; return true; }
        catch (InvalidDataException) { return false; }
    }
    finally { File.Delete(target); }
}
Assert(await AdmitHeaderD04Async("{\"a\":{\"dtype\":\"F32\",\"data_offsets\":[0,4]},\"b\":{\"dtype\":\"F32\",\"data_offsets\":[4,8]}}",8),
    "D04 two separate tensor ranges admitted");
Assert(!await AdmitHeaderD04Async("{\"a\":{\"data_offsets\":[0,4]},\"a\":{\"data_offsets\":[4,8]}}",8),
    "D04 duplicate tensor field rejected");
Assert(!await AdmitHeaderD04Async("{\"a\":{\"data_offsets\":[0,4],\"data_offsets\":[4,8]}}",8),
    "D04 duplicate nested offsets rejected");
Assert(!await AdmitHeaderD04Async("{\"a\":{\"data_offsets\":[0,4]},\"b\":{\"data_offsets\":[2,6]}}",8),
    "D04 overlapping tensor ranges rejected");

// R99: a non-default HTTPS port is a different official-source origin.
// This is a focused reviewed-registry source test, not installed-model proof.
var reviewedOrigin = new ModelArtifactReviewCandidate(
    FamilyId: "tinyllama", OfficialSourceUrl: "https://ollama.com/library/tinyllama",
    ExactTag: "tinyllama:test-r99", Version: "test-r99",
    LicenseId: "test-fixture", LicenseEvidenceUrl: "https://ollama.com/library/tinyllama",
    ArtifactBytes: 1024, RequiredDiskBytes: 2048, RecommendedRamBytes: 4096,
    RecommendedVramBytes: null, ArtifactSha256: new string('a', 64),
    ManifestSha256: new string('b', 64),
    CompatibilityEvidenceUrl: "https://ollama.com/library/tinyllama",
    ImmutableRevision: "sha256:" + new string('b', 64),
    CompatibilityReviewed: true, ReviewerReceiptId: "r99-fixture",
    ReviewStatus: "OWNER_VERIFIED");
Assert(ModelArtifactReviewRegistry.TryPromote(reviewedOrigin, true, out var canonicalReviewed)
    && canonicalReviewed?.CanOfferOneClickPull == true,
    "R99 canonical owner-reviewed source accepted");
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { OfficialSourceUrl = "https://ollama.com:444/library/tinyllama" },
    true, out _),
    "R99 nondefault Ollama port rejected");
Assert(!ModelArtifactReviewRegistry.TryPromote(reviewedOrigin, false, out _),
    "R99 native-reviewed receipt still required");
Assert(canonicalReviewed is not null &&
    !(canonicalReviewed with { ReviewedRightsReceiptId = null }).CanOfferOneClickPull &&
    !(canonicalReviewed with { ReviewedRightsReceiptId = "  " }).CanOfferOneClickPull &&
    !(canonicalReviewed with { ReviewedRightsReceiptId = new string('r', 129) }).CanOfferOneClickPull &&
    !(canonicalReviewed with { ReviewedRightsReceiptId = "owner\nspoofed" }).CanOfferOneClickPull,
    "R99A unverified public model record must fail closed");
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { ReviewerReceiptId = "owner\nspoofed" }, true, out _),
    "D04 native owner reviewer control-character receipt rejected");

// D04 R5: untrusted reviewed-registry evidence URLs are not native rights proof.
// TryPromote must reject every local, altered-origin or privileged endpoint.
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { LicenseEvidenceUrl = "https://127.0.0.1/license" }, true, out _),
    "D04 reviewed-license loopback IP denied");
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { CompatibilityEvidenceUrl = "https://[::1]/compat" }, true, out _),
    "D04 compatibility IPv6 loopback denied");
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { LicenseEvidenceUrl = "https://models.local/license" }, true, out _),
    "D04 reviewed-license mDNS local denied");
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { CompatibilityEvidenceUrl = "https://rights.internal/compat" }, true, out _),
    "D04 private compatibility domain denied");
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { LicenseEvidenceUrl = "https://localhost/license" }, true, out _),
    "D04 localhost rights evidence denied");
Assert(!ModelArtifactReviewRegistry.TryPromote(
    reviewedOrigin with { LicenseEvidenceUrl = "https://ollama.com:444/license" }, true, out _),
    "D04 nonstandard port rights evidence denied");
Assert(ModelArtifactReviewRegistry.TryPromote(reviewedOrigin, true, out _),
    "D04 legitimate owner-reviewed public HTTPS evidence preserved");

using var correct = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"sha256:" + new string('a',64) + "\"}]}");
Assert(ModelLocalAttestation.ParseUnambiguousModelDigest(correct.RootElement, "m:1") == "sha256:" + new string('a',64), "T01 pinned local digest");

// D04 R5: a last-wins /api/tags JSON property is not unique model evidence.
using var d04DuplicateRoot = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"" +
    new string('b',64) + "\"}],\"models\":[{\"name\":\"m:1\",\"digest\":\"" +
    new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(d04DuplicateRoot.RootElement, "m:1"),
    "D04 duplicate top-level models arrays HOLD");
using var d04DuplicateName = JsonDocument.Parse("{\"models\":[{\"name\":\"decoy:1\",\"name\":\"m:1\",\"digest\":\"" +
    new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(d04DuplicateName.RootElement, "m:1"),
    "D04 duplicate model identity HOLD");
using var d04DuplicateDigest = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"" +
    new string('b',64) + "\",\"digest\":\"" + new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(d04DuplicateDigest.RootElement, "m:1"),
    "D04 duplicate local digest SHA HOLD");

 // B04 R5: case-folded aliases must never turn /api/tags into false
 // verified absence or a competing owner's installed-model digest.
using var b04TagsRootAlias = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"" +
    new string('a',64) + "\"}],\"Models\":[]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(b04TagsRootAlias.RootElement, "m:1"),
    "B04 case-aliased models array cannot attest local model");
using var b04TagsNameAlias = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"Name\":\"decoy:1\",\"digest\":\"" +
    new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(b04TagsNameAlias.RootElement, "m:1"),
    "B04 case-aliased model name cannot attest owner identity");
using var b04TagsDigestAlias = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"" +
    new string('a',64) + "\",\"Digest\":\"" + new string('b',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(b04TagsDigestAlias.RootElement, "m:1"),
    "B04 case-aliased digest cannot attest installed weights");



 // B04: /api/tags case variants are NOT evidence of absence. The native queue
 // serializes the same installation tag using OrdinalIgnoreCase.
using var b04CaseAlias = JsonDocument.Parse("{\"models\":[{\"name\":\"M:1\",\"digest\":\"" + new string('a',64) + "\"}]}");
Assert(ModelLocalAttestation.ParseUnambiguousModelDigest(b04CaseAlias.RootElement, "m:1") ==
    "sha256:" + new string('a',64),
    "B04 case-varied installed owner tag must never appear absent");
using var b04CaseCollision = JsonDocument.Parse("{\"models\":[{\"name\":\"M:1\",\"digest\":\"" +
    new string('a',64) + "\"},{\"name\":\"m:1\",\"digest\":\"" +
    new string('b',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(b04CaseCollision.RootElement, "m:1"),
    "B04 case-alias duplicate installed tags fail closed before Ollama mutation");
using var officialBareTags = JsonDocument.Parse("{\"models\":[{\"name\":\"gemma4\",\"digest\":\"c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb\"}]}");
Assert(ModelLocalAttestation.ParseUnambiguousModelDigest(officialBareTags.RootElement, "gemma4") ==
    "sha256:c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb", "T01B Ollama official bare digest normalized");
using var malformedBareTags = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"" + new string('a', 63) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(malformedBareTags.RootElement, "m:1"),
    "T01C truncated bare digest rejected");
using var wrongAlgorithmTags = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"sha1:" + new string('a', 64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(wrongAlgorithmTags.RootElement, "m:1"),
    "T01D unsupported algorithm digest rejected");
using var mixedDuplicateTags = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"" + new string('a',64) +
    "\"},{\"name\":\"m:1\",\"digest\":\"sha256:" + new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(mixedDuplicateTags.RootElement, "m:1"),
    "T01E mixed bare/prefixed duplicate denied");
Assert(ModelLocalAttestation.ParseUnambiguousModelDigest(correct.RootElement, "missing:1") is null, "T02 absent tag stays unknown");
using var duplicated = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"sha256:" + new string('a',64) + "\"},{\"name\":\"m:1\",\"digest\":\"sha256:" + new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(duplicated.RootElement,"m:1"), "T03 duplicate tag denied");
using var invalidSchema = JsonDocument.Parse("{\"models\":{}}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(invalidSchema.RootElement,"m:1"), "T04 nonarray tags denied");
using var invalidDigest = JsonDocument.Parse("{\"models\":[{\"name\":\"m:1\",\"digest\":\"sha256:broken\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(invalidDigest.RootElement,"m:1"), "T05 malformed digest denied");
using var missingName = JsonDocument.Parse("{\"models\":[{\"digest\":\"sha256:" + new string('a',64) + "\"}]}");
MustReject(() => ModelLocalAttestation.ParseUnambiguousModelDigest(missingName.RootElement,"m:1"), "T06 malformed record denied");
var root = Path.Combine(Path.GetTempPath(),"NOX_P03_HARDEN_"+Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try {
  var file = Path.Combine(root,"valid.gguf"); await File.WriteAllTextAsync(file,"GGUFtest");
  ModelLocalAttestation.RequireRegularUnlinkedFile(file); Assert(true,"T07 regular GGUF allowed");
  var link = Path.Combine(root,"link.gguf");
  try {
    File.CreateSymbolicLink(link, file);
    MustReject(() => ModelLocalAttestation.RequireRegularUnlinkedFile(link),"T08 symlink GGUF denied");
  } catch (UnauthorizedAccessException) { Console.WriteLine("SKIP T08 Windows symlink privilege unavailable"); }
  if (OperatingSystem.IsWindows())
  {
    var alias = Path.Combine(root, "foreign-alias.gguf");
    if (!P03HardlinkProbe.Create(alias, file, IntPtr.Zero))
        throw new InvalidOperationException("P03_HARDLINK_TEST_SETUP_FAILED");
    MustReject(() => ModelLocalAttestation.RequireRegularUnlinkedFile(file),
        "T08B owner GGUF with foreign hardlink denied");
    MustReject(() => ModelLocalAttestation.RequireRegularUnlinkedFile(alias),
        "T08C alias GGUF denied");
    File.Delete(alias);
    ModelLocalAttestation.RequireRegularUnlinkedFile(file);
    Assert(true, "T08D original GGUF admitted after alias removed");
  }
  async Task RejectAsyncReceiptHardlink(string path, ModelInstallReceipt expected)
  {
    try { await ModelLocalAttestation.VerifyReceiptAsync(path, expected, default); }
    catch (InvalidDataException) { Assert(true, "T08E foreign receipt hardlink denied"); return; }
    throw new Exception("FAIL T08E receipt hardlink accepted");
  }
  var receipt = new ModelInstallReceipt("NOX_P03_INSTALL_RECEIPT_V1",Guid.NewGuid(),"m:1","ollama-pull",
      DateTimeOffset.UtcNow,null,null,"sha256:"+new string('a',64),"https://ollama.com/library/m","http://localhost:11434/");
  var receiptFile = Path.Combine(root,"receipt.json");
  await File.WriteAllTextAsync(receiptFile,JsonSerializer.Serialize(receipt,new JsonSerializerOptions(JsonSerializerDefaults.Web)));
  if (OperatingSystem.IsWindows())
  {
    var alias = Path.Combine(root, "foreign-receipt-alias.json");
    if (!P03HardlinkProbe.Create(alias, receiptFile, IntPtr.Zero))
        throw new InvalidOperationException("P03_RECEIPT_HARDLINK_TEST_SETUP_FAILED");
    await RejectAsyncReceiptHardlink(receiptFile, receipt);
    await RejectAsyncReceiptHardlink(alias, receipt);
    File.Delete(alias);
  }
  // Owner-pinned artifact registry and review-template reads must never
  // consume a foreign NTFS hardlink (even with a matching expected SHA).
  var registryFile = Path.Combine(root, "reviewed-artifacts.json");
  var registryText = "{\"schema\":\"NOX-P03-REVIEWED-ARTIFACTS-V1\",\"items\":[]}";
  await File.WriteAllTextAsync(registryFile, registryText);
  var registryPin = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
      Encoding.UTF8.GetBytes(registryText)));
  Assert(ModelArtifactReviewRegistry.LoadReviewedArtifacts(registryFile, registryPin).Count == 0,
      "T08F owner-pinned empty registry remains review-required");
  // D04: SourceLock must not admit two owner-reviewed entries whose Ollama
  // model tags alias under case-insensitive queue identity. Ordinary distinct
  // reviewed tags remain usable; the negative fixture is SHA-pinned too.
  var collisionFile = Path.Combine(root, "reviewed-case-collision.json");
  async Task<string> WriteReviewedCollisionFixtureAsync(ModelArtifactReviewCandidate[] values)
  {
      var body = JsonSerializer.Serialize(new {
          schema = "NOX-P03-REVIEWED-ARTIFACTS-V1", items = values
      }, new JsonSerializerOptions(JsonSerializerDefaults.Web));
      await File.WriteAllTextAsync(collisionFile, body);
      return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
          Encoding.UTF8.GetBytes(body)));
  }
  var distinctReview = reviewedOrigin with { ExactTag = "tinyllama:test-r100",
      Version = "test-r100", ReviewerReceiptId = "r100-fixture" };
  var distinctReviewPin = await WriteReviewedCollisionFixtureAsync(
      new[] { reviewedOrigin, distinctReview });
  Assert(ModelArtifactReviewRegistry.LoadReviewedArtifacts(collisionFile, distinctReviewPin).Count == 2,
      "T08F1 distinct owner-reviewed tags survive registry admission");
  var aliasReview = distinctReview with { ExactTag = "TinyLlama:test-r99",
      ReviewerReceiptId = "r99-case-alias" };
  var collisionPin = await WriteReviewedCollisionFixtureAsync(
      new[] { reviewedOrigin, aliasReview });
  MustReject(() => ModelArtifactReviewRegistry.LoadReviewedArtifacts(collisionFile, collisionPin),
      "T08F2 case-colliding owner-reviewed tags fail closed");
  var templateFile = Path.Combine(root, "review-template.json");
  await File.WriteAllTextAsync(templateFile, "{\"items\":[]}");
  if (OperatingSystem.IsWindows())
  {
    void RequireHardlinkHold(Action action, string label)
    {
      try { action(); }
      catch (InvalidDataException ex) when (ex.Message == "P03_MODEL_FOREIGN_HARDLINK_HOLD")
      { Assert(true, label); return; }
      throw new Exception("FAIL " + label + ": missing exact hardlink HOLD");
    }
    var registryAlias = Path.Combine(root, "foreign-registry-alias.json");
    if (!P03HardlinkProbe.Create(registryAlias, registryFile, IntPtr.Zero))
        throw new InvalidOperationException("P03_REVIEW_REGISTRY_HARDLINK_TEST_SETUP_FAILED");
    RequireHardlinkHold(
        () => ModelArtifactReviewRegistry.LoadReviewedArtifacts(registryFile, registryPin),
        "T08G reviewed registry with foreign hardlink denied on open handle");
    File.Delete(registryAlias);
    var templateAlias = Path.Combine(root, "foreign-template-alias.json");
    if (!P03HardlinkProbe.Create(templateAlias, templateFile, IntPtr.Zero))
        throw new InvalidOperationException("P03_REVIEW_TEMPLATE_HARDLINK_TEST_SETUP_FAILED");
    RequireHardlinkHold(() => ModelArtifactReviewRegistry.ReadTemplate(templateFile),
        "T08H untrusted review template hardlink denied before JSON parsing");
    File.Delete(templateAlias);
  }
  await ModelLocalAttestation.VerifyReceiptAsync(receiptFile, receipt, default);
  Assert(true,"T09 install receipt readback");
  try { await ModelLocalAttestation.VerifyReceiptAsync(receiptFile,receipt with { ModelTag="attacker:tag" },default); throw new Exception("FAIL T10"); }
  catch (InvalidDataException) { Assert(true,"T10 receipt mismatch denied"); }
} finally { Directory.Delete(root,recursive:true); }
// D04: independent job IDs must not hide two simultaneously active pulls
// for one Ollama tag, including case variants imported from old queue backups.
// Terminal historic entries must remain readable (NO-LOSS).
var d04Root = Path.Combine(Path.GetTempPath(), "NOX_P03_ACTIVE_TAG_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(d04Root);
try
{
    var d04Store = new ModelDownloadQueueStore(d04Root);
    var d04File = Path.Combine(d04Root, "p03-model-download-queue.json");
    var d04Now = DateTimeOffset.UtcNow;
    var d04First = new ModelJob(Guid.NewGuid(), ModelJobKind.OllamaPull,
        "tinyllama:reviewed-a", null, true, "https://ollama.com/library/tinyllama",
        d04Now, d04Now, ModelJobState.Queued,
        ExpectedOllamaDigest: new string('a', 64),
        ImmutableRevision: "sha256:" + new string('a', 64), RightsReceiptId: "owner-a");
    var d04Second = d04First with { Id = Guid.NewGuid(),
        ModelTag = "tinyllama:reviewed-b", State = ModelJobState.Running,
        RightsReceiptId = "owner-b" };
    async Task D04WriteAsync(params ModelJob[] jobs) =>
        await File.WriteAllTextAsync(d04File, JsonSerializer.Serialize(jobs,
            new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    await D04WriteAsync(d04First, d04Second);
    Assert((await d04Store.ReadAsync()).Count == 2,
        "D04A distinct concurrently active reviewed tags remain readable");
    await D04WriteAsync(d04First, d04Second with { ModelTag = "TinyLlama:reviewed-a" });
    var d04CaseRejected = false;
    try { _ = await d04Store.ReadAsync(); }
    catch (InvalidDataException e) when (e.Message == "P03_QUEUE_ACTIVE_TAG_ALIAS_HOLD")
    { d04CaseRejected = true; }
    Assert(d04CaseRejected, "D04B case-aliased live pull IDs fail closed");
    await D04WriteAsync(d04First, d04Second with { ModelTag = d04First.ModelTag,
        State = ModelJobState.Cancelling });
    var d04StopRejected = false;
    try { _ = await d04Store.ReadAsync(); }
    catch (InvalidDataException e) when (e.Message == "P03_QUEUE_ACTIVE_TAG_ALIAS_HOLD")
    { d04StopRejected = true; }
    Assert(d04StopRejected, "D04C STOP-pending alias cannot coexist with a queued pull");
    await D04WriteAsync(d04First, d04Second with { ModelTag = d04First.ModelTag,
        State = ModelJobState.Completed });
    Assert((await d04Store.ReadAsync()).Count == 2,
        "D04D terminal same-tag history preserved without reactivating");
    var d04CrossKind = d04Second with { Kind = ModelJobKind.GgufImport,
        ModelTag = "TINYLLAMA:reviewed-a", LocalPath = Path.Combine(d04Root, "candidate.gguf"),
        ExpectedLocalBytes = 32, ExpectedLocalSha256 = new string('b', 64),
        ExpectedOllamaDigest = null, ImmutableRevision = null };
    await D04WriteAsync(d04First, d04CrossKind);
    var d04MixedDenied = false;
    try { _ = await d04Store.ReadAsync(); }
    catch (InvalidDataException e) when (e.Message == "P03_QUEUE_ACTIVE_TAG_ALIAS_HOLD")
    { d04MixedDenied = true; }
    Assert(d04MixedDenied, "D04E pull/GGUF active case-alias fails closed");
    await D04WriteAsync(d04First, d04CrossKind with { State = ModelJobState.Completed });
    Assert((await d04Store.ReadAsync()).Count == 2,
        "D04F completed GGUF same-tag history remains readable");
    // Durable queue/backup JSON uses case-insensitive Web deserialization;
    // ambiguous last-wins keys must fail closed without replacing any bytes.
    var d04CanonicalJson = JsonSerializer.Serialize(d04First,
        new JsonSerializerOptions(JsonSerializerDefaults.Web));
    const string d04TagKey = "\"modelTag\":";
    const string d04RightsKey = "\"rightsReceiptId\":";
    if (!d04CanonicalJson.Contains(d04TagKey, StringComparison.Ordinal) ||
        !d04CanonicalJson.Contains(d04RightsKey, StringComparison.Ordinal))
        throw new Exception("D04 queue JSON regression fixture drift");
    var d04Duplicate = d04CanonicalJson.Replace(d04TagKey,
        "\"modelTag\":\"decoy:tag\",\"modelTag\":", StringComparison.Ordinal);
    await File.WriteAllTextAsync(d04File, "[" + d04Duplicate + "]");
    var d04DuplicateDenied = false;
    try { _ = await d04Store.ReadAsync(); }
    catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_DUPLICATE_JSON_FIELD_HOLD")
    { d04DuplicateDenied = true; }
    Assert(d04DuplicateDenied, "D04I duplicate modelTag from saved queue denied");

    var d04CaseAlias = d04CanonicalJson.Replace(d04RightsKey,
        "\"RightsReceiptId\":\"revoked\",\"rightsReceiptId\":", StringComparison.Ordinal);
    await File.WriteAllTextAsync(d04File, "[" + d04CaseAlias + "]");
    var d04CaseAliasDenied = false;
    try { _ = await d04Store.ReadAsync(); }
    catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_DUPLICATE_JSON_FIELD_HOLD")
    { d04CaseAliasDenied = true; }
    Assert(d04CaseAliasDenied, "D04J case-insensitive rights receipt alias denied");

    var d04NestedAlias = d04CanonicalJson.Replace(d04TagKey,
        "\"untrustedMetadata\":{\"digest\":\"a\",\"digest\":\"b\"},\"modelTag\":",
        StringComparison.Ordinal);
    await File.WriteAllTextAsync(d04File, "[" + d04NestedAlias + "]");
    var d04NestedDenied = false;
    try { _ = await d04Store.ReadAsync(); }
    catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_DUPLICATE_JSON_FIELD_HOLD")
    { d04NestedDenied = true; }
    Assert(d04NestedDenied, "D04K nested ambiguous metadata denied");

    await D04WriteAsync(d04First);
    var d04OriginalBytes = await File.ReadAllBytesAsync(d04File);
    await File.WriteAllTextAsync(d04File + ".bak", "[" + d04Duplicate + "]");
    var d04BackupDenied = false;
    try { await d04Store.RestoreBackupAsync(true); }
    catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_DUPLICATE_JSON_FIELD_HOLD")
    { d04BackupDenied = true; }
    Assert(d04BackupDenied &&
        (await File.ReadAllBytesAsync(d04File)).SequenceEqual(d04OriginalBytes),
        "D04L invalid backup denied with live queue NO-LOSS");

}
finally { Directory.Delete(d04Root, recursive: true); }
Console.WriteLine($"P03_HARDENING_SMOKE_PASS {pass} verified assertions");

// TURBO13 protocol and immutable receipt tests; each uses actual source methods.
int turbo13Pass = 0;
void T13(bool ok, string label) { if (!ok) throw new Exception("FAIL " + label); turbo13Pass++; Console.WriteLine("PASS " + label); }
async Task RejectAsync(Func<Task> test, string label)
{
    try { await test(); }
    catch (InvalidDataException) { T13(true, label); return; }
    throw new Exception("FAIL " + label);
}
async Task Drain(string input)
{
    using var reader = new StringReader(input);
    await foreach (var _ in ModelLocalAttestation.ReadValidatedStreamAsync(reader)) { }
}
// 01. Two valid records across buffer boundaries and CRLF preserve exact fields.
var goodLine = "{\"status\":\"downloading\",\"digest\":\"sha256:" + new string('a',64) + "\",\"completed\":1,\"total\":2}";
using (var reader = new StringReader(goodLine + "\r\n{\"status\":\"success\"}"))
{
    var updates = new List<OllamaStreamUpdate>();
    await foreach (var evt in ModelLocalAttestation.ReadValidatedStreamAsync(reader)) updates.Add(evt);
    T13(updates.Count == 2 && updates[0].Completed == 1 && updates[1].Status == "success", "T13-01 bounded valid CRLF stream");
}
// B04 R5: duplicate Ollama NDJSON control properties must never use last-wins.
// These are original ModelLocalAttestation methods, not a fake provider.
void RequireStreamDuplicateControlHold(string json, string name)
{
    try { ModelLocalAttestation.ParseVerifiedEvent(json); }
    catch (InvalidDataException ex) when (ex.Message == "OLLAMA_STREAM_DUPLICATE_CONTROL_FIELD_HOLD")
    { Assert(true, name); return; }
    throw new Exception("FAIL " + name);
}
RequireStreamDuplicateControlHold("{\"status\":\"error\",\"status\":\"success\"}",
    "B04 duplicate status cannot forge success");
RequireStreamDuplicateControlHold("{\"status\":\"downloading\",\"error\":\"disk error\",\"error\":\"\"}",
    "B04 duplicate error cannot hide provider failure");
RequireStreamDuplicateControlHold("{\"digest\":\"sha256:" + new string('a', 64) + "\",\"digest\":\"sha256:" + new string('b', 64) + "\"}",
    "B04 duplicate digest cannot disguise installed layer");
RequireStreamDuplicateControlHold("{\"completed\":1,\"completed\":2,\"total\":3}",
    "B04 duplicate completed cannot forge progress");
RequireStreamDuplicateControlHold("{\"completed\":7,\"total\":5,\"total\":10}",
    "B04 duplicate total cannot hide impossible progress");
RequireStreamDuplicateControlHold("{\"\\u0073tatus\":\"error\",\"status\":\"success\"}",
    "B04 escaped duplicate status is not unique owner evidence");
// B04 R5: duplicate case-alias controls can forge an installed-model success
// or mask an Ollama offline error; deny them before parsing the final event.
RequireStreamDuplicateControlHold("{\"status\":\"success\",\"Status\":\"error\"}",
    "B04 case-aliased status cannot forge completed pull");
RequireStreamDuplicateControlHold("{\"status\":\"downloading\",\"error\":\"\",\"Error\":\"network down\"}",
    "B04 case-aliased error cannot hide offline provider");
RequireStreamDuplicateControlHold("{\"digest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"Digest\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"}",
    "B04 case-aliased layer digest must fail closed");
RequireStreamDuplicateControlHold("{\"status\":\"downloading\",\"completed\":1,\"Completed\":2,\"total\":3}",
    "B04 case-aliased completed count must fail closed");
RequireStreamDuplicateControlHold("{\"completed\":2,\"total\":3,\"Total\":4}",
    "B04 case-aliased total count must fail closed");
Assert(ModelLocalAttestation.ParseVerifiedEvent("{\"status\":\"downloading\",\"note\":1,\"note\":2}").Status == "downloading",
    "B04 non-control metadata leaves standard stream status valid");
// 02. Oversized first line without a terminator fails before unbounded allocation.
await RejectAsync(() => Drain(new string('x', ModelLocalAttestation.MaxEventCharacters + 1)),
    "T13-02 oversized no-newline line denied");
// 03. Numeric status must be rejected, not reported as a completed download.
await RejectAsync(() => Drain("{\"status\":17}\n"), "T13-03 typed status enforced");
// 04. Negative byte progress is invalid.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"completed\":-1,\"total\":1}\n"),
    "T13-04 negative progress denied");
// 05. Completed bytes must not exceed the total.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"completed\":5,\"total\":2}\n"),
    "T13-05 impossible progress denied");
// 06. A progress layer's digest must be a complete SHA-256.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"digest\":\"sha256:xyz\"}\n"),
    "T13-06 fake layer digest denied");
// 07. Error must be text, not a nested object that bypasses the error branch.
await RejectAsync(() => Drain("{\"status\":\"pulling\",\"error\":{}}\n"),
    "T13-07 nonstring error denied");
// 08. A forged second success or arbitrary event after success is rejected.
await RejectAsync(() => Drain("{\"status\":\"success\"}\n{\"status\":\"success\"}\n"),
    "T13-08 duplicate terminal success denied");
// 09. Full timestamp on persisted installation evidence is immutable.
var attestationRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_T13_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(attestationRoot);
try
{
    var r = new ModelInstallReceipt("NOX_P03_INSTALL_RECEIPT_V1", Guid.NewGuid(), "m:1", "gguf-import",
        DateTimeOffset.UtcNow, 8, new string('a',64), "sha256:"+new string('b',64),
        "https://ollama.com/library/m", "http://localhost:11434/");
    await ModelLocalAttestation.WriteNewReceiptAsync(attestationRoot, r, default);
    await RejectAsync(() => ModelLocalAttestation.VerifyReceiptAsync(
        Path.Combine(attestationRoot, r.JobId.ToString("N")+".json"),
        r with { CompletedAtUtc = r.CompletedAtUtc.AddMinutes(1) }, default),
        "T13-09 receipt timestamp mutation denied");
    // 10. A later concurrent operation cannot silently replace an earlier receipt.
    bool duplicateBlocked = false;
    try { await ModelLocalAttestation.WriteNewReceiptAsync(attestationRoot, r, default); }
    catch (IOException) { duplicateBlocked = true; }
    await ModelLocalAttestation.VerifyReceiptAsync(Path.Combine(attestationRoot, r.JobId.ToString("N")+".json"), r, default);
    T13(duplicateBlocked, "T13-10 immutable receipt no overwrite");
}
finally { Directory.Delete(attestationRoot, recursive:true); }
Console.WriteLine($"P03_TURBO13_SMOKE_PASS {turbo13Pass}/10 targeted assertions");

 // E03 final: multiple NOX windows share one persisted queue; no lost updates.
var multiRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_MULTI_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(multiRoot);
try
{
    var a = new ModelDownloadQueueStore(multiRoot);
    var b = new ModelDownloadQueueStore(multiRoot);
    var evidence = "https://ollama.com/library/tinyllama";
    var digestA = new string('a', 64);
    var digestB = new string('b', 64);
    var model = ModelCatalog.Get("tinyllama") with {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:1.1b", Version = "synthetic-fixture", License = "fixture-license",
        ArtifactBytes = 100, RequiredDiskBytes = 200, RecommendedRamBytes = 300,
        ExpectedSha256 = digestB, ExpectedManifestDigestSha256 = digestA,
        ImmutableRevision = "sha256:" + digestA, CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri(evidence), CompatibilityEvidenceUri = new Uri(evidence), ReviewedRightsReceiptId = "rights-fixture"
    };
    var injectedReceiptDenied = false;
    try { await a.EnqueueVerifiedPullAsync(model with {
        ReviewedRightsReceiptId = "owner\nspoofed" }, true); }
    catch (InvalidOperationException) { injectedReceiptDenied = true; }
    Assert(injectedReceiptDenied && (await a.ReadAsync()).Count == 0,
        "D04 untrusted pull rights ID never persisted");
    var sameJobs = await Task.WhenAll(Enumerable.Range(0, 20).Select(i =>
        (i % 2 == 0 ? a : b).EnqueueVerifiedPullAsync(model, true)));
    Assert(sameJobs.Select(j => j.Id).Distinct().Count() == 1,
        "F01 multiple instances deduplicate immutable Pull");
    Assert((await new ModelDownloadQueueStore(multiRoot).ReadAsync()).Count == 1,
        "F02 queue stays durable across independent instances");
    // G2 NO-LOSS: a .bak hardlink is not a reparse point. Backup rotation
    // must not modify the separate target file's bytes.
    if (OperatingSystem.IsWindows())
    {
        var linkRoot = Path.Combine(multiRoot, "backup-hardlink");
        var unrelated = Path.Combine(multiRoot, "other-owner-untouched.txt");
        const string sentinel = "P03_UNRELATED_OWNER_DATA_MUST_NOT_CHANGE";
        await File.WriteAllTextAsync(unrelated, sentinel);
        var protectedQueue = new ModelDownloadQueueStore(linkRoot);
        var originalJob = await protectedQueue.EnqueueVerifiedPullAsync(model, true);
        var backupAlias = Path.Combine(linkRoot, "p03-model-download-queue.json.bak");
        if (!P03HardlinkFixture.CreateHardLink(backupAlias, unrelated, IntPtr.Zero))
            throw new Exception("FAIL F02A hardlink fixture unavailable");
        var changed = await protectedQueue.UpdateAsync(originalJob.Id,
            j => j with { Status = "Backup rotated" });
        Assert(changed?.Status == "Backup rotated" &&
            (await protectedQueue.ReadAsync()).Single().Status == changed.Status,
            "F02A model queue remains durable");
        Assert(await File.ReadAllTextAsync(unrelated) == sentinel &&
            (await File.ReadAllTextAsync(backupAlias)).Contains(
                originalJob.Id.ToString("D"), StringComparison.OrdinalIgnoreCase),
            "F02B foreign bytes preserved through queue backup rotation");
        var liveQueue = Path.Combine(linkRoot, "p03-model-download-queue.json");
        var beforeRestore = await File.ReadAllBytesAsync(liveQueue);
        var foreignBackup = Path.Combine(multiRoot, "foreign-owner-valid-backup.json");
        File.Move(backupAlias, foreignBackup);
        if (!P03HardlinkFixture.CreateHardLink(backupAlias, foreignBackup, IntPtr.Zero))
            throw new Exception("FAIL F02C backup hardlink fixture unavailable");
        try
        {
            await protectedQueue.RestoreBackupAsync(true);
            throw new Exception("FAIL F02C hardlinked backup accepted");
        }
        catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_HARDLINK_SNAPSHOT_HOLD")
        {
            Assert(true, "F02C foreign hardlinked backup refused before read");
        }
        Assert((await File.ReadAllBytesAsync(liveQueue)).SequenceEqual(beforeRestore),
            "F02C original queue preserved after backup refusal");
        var foreignQueue = Path.Combine(multiRoot, "foreign-owner-valid-live.json");
        File.Move(liveQueue, foreignQueue);
        if (!P03HardlinkFixture.CreateHardLink(liveQueue, foreignQueue, IntPtr.Zero))
            throw new Exception("FAIL F02D live hardlink fixture unavailable");
        try
        {
            await protectedQueue.ReadAsync();
            throw new Exception("FAIL F02D hardlinked live queue accepted");
        }
        catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_HARDLINK_SNAPSHOT_HOLD")
        {
            Assert(true, "F02D foreign hardlinked live queue refused before read");
        }
        File.Delete(liveQueue); // ephemeral fixture alias, not target data
        File.Move(foreignQueue, liveQueue);
        Assert((await protectedQueue.ReadAsync()).Single().Status == "Backup rotated",
            "F02D normal queue survives hardlink rejection");
        // F02E: even a well-formed queue reached through a HARDLINK is not
        // an owner-authorized snapshot for rollback; do not copy it to .pre_restore.
        File.Delete(backupAlias); // only the disposable hardlink alias
        File.Move(foreignBackup, backupAlias); // trusted single-link backup
        var sourceBefore = await File.ReadAllBytesAsync(liveQueue);
        var preservedBefore = Directory.GetFiles(linkRoot, "*.pre_restore.*").Length;
        File.Move(liveQueue, foreignQueue);
        if (!P03HardlinkFixture.CreateHardLink(liveQueue, foreignQueue, IntPtr.Zero))
            throw new Exception("FAIL F02E live hardlink fixture unavailable");
        try
        {
            await protectedQueue.RestoreBackupAsync(true);
            throw new Exception("FAIL F02E hardlinked live snapshot accepted");
        }
        catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_HARDLINK_SNAPSHOT_HOLD")
        {
            Assert(true, "F02E rollback refuses a hardlinked current snapshot");
        }
        Assert((await File.ReadAllBytesAsync(foreignQueue)).SequenceEqual(sourceBefore) &&
            Directory.GetFiles(linkRoot, "*.pre_restore.*").Length == preservedBefore,
            "F02E no foreign snapshot copied and no data altered");
        File.Delete(liveQueue); // only the disposable alias, not foreign bytes
        File.Move(foreignQueue, liveQueue);

        // D04 R5: both durable lock namespaces carry native queue authority.
        // An existing NTFS hardlink must not be accepted as an owned lease.
        var executionForeign = Path.Combine(multiRoot, "d04-foreign-execution-lock.dat");
        const string executionSentinel = "P03_FOREIGN_EXECUTION_LEASE_UNTOUCHED";
        await File.WriteAllTextAsync(executionForeign, executionSentinel);
        var executionAlias = Path.Combine(linkRoot,
            "p03-model-download-queue.json.running." + originalJob.Id.ToString("N") + ".lock");
        if (!P03HardlinkFixture.CreateHardLink(executionAlias, executionForeign, IntPtr.Zero))
            throw new Exception("FAIL D04F foreign execution lock fixture unavailable");
        try
        {
            using var deniedLease = protectedQueue.TryAcquireExecutionLease(originalJob.Id);
            throw new Exception("FAIL D04F foreign execution hardlink lease admitted");
        }
        catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_HARDLINK_SNAPSHOT_HOLD")
        {
            Assert(true, "D04F foreign execution hardlink denied on opened handle");
        }
        finally { File.Delete(executionAlias); } // Disposable alias, not foreign bytes.
        Assert(await File.ReadAllTextAsync(executionForeign) == executionSentinel,
            "D04G execution lease failure preserved unrelated owner bytes");
        using (var nativeLease = protectedQueue.TryAcquireExecutionLease(originalJob.Id))
            Assert(nativeLease is not null, "D04H ordinary single-link execution lease works");

        var globalLeaseFile = Path.Combine(linkRoot, "p03-model-download-queue.json.lock");
        var savedGlobalLease = Path.Combine(linkRoot, "d04-owner-queue-lock.saved");
        var queueForeign = Path.Combine(multiRoot, "d04-foreign-queue-lock.dat");
        const string queueSentinel = "P03_FOREIGN_QUEUE_LEASE_UNTOUCHED";
        await File.WriteAllTextAsync(queueForeign, queueSentinel);
        File.Move(globalLeaseFile, savedGlobalLease);
        try
        {
            if (!P03HardlinkFixture.CreateHardLink(globalLeaseFile, queueForeign, IntPtr.Zero))
                throw new Exception("FAIL D04I foreign queue lock fixture unavailable");
            try
            {
                _ = await protectedQueue.ReadAsync();
                throw new Exception("FAIL D04I foreign queue hardlink lease admitted");
            }
            catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_HARDLINK_SNAPSHOT_HOLD")
            {
                Assert(true, "D04I foreign queue hardlink denied before queue read");
            }
        }
        finally
        {
            if (File.Exists(globalLeaseFile)) File.Delete(globalLeaseFile);
            File.Move(savedGlobalLease, globalLeaseFile); // Restore original inode.
        }
        Assert(await File.ReadAllTextAsync(queueForeign) == queueSentinel &&
            (await protectedQueue.ReadAsync()).Single().Id == originalJob.Id,
            "D04J foreign queue lock untouched; legitimate queue remains readable");
    }
    var file = Path.Combine(multiRoot, "sample.gguf");
    await File.WriteAllBytesAsync(file, Encoding.ASCII.GetBytes("GGUFsynthetic-byteproof"));
    var sha = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(file))).ToLowerInvariant();
    var size = new FileInfo(file).Length;
    // D04: queue admission previously persisted credentials/oversized IDs that
    // the existing Ollama adapter would reject only AFTER owner approval.
    var deniedGgufBaseline = (await a.ReadAsync()).Count;
    // D04: relative GGUF input previously became an absolute path before admission.
    // Native reviewed paths must not depend on current working directory.
    var d04RelativeGguf = Path.GetRelativePath(Environment.CurrentDirectory, file);
    Assert(!Path.IsPathFullyQualified(d04RelativeGguf),
        "D04 native relative-path negative fixture is genuinely relative");
    var d04RelativeRejected = false;
    try { await a.EnqueueVerifiedGgufAsync("local:relative-denied", d04RelativeGguf,
        size, sha, "reviewed", evidence); }
    catch (InvalidDataException ex) when (ex.Message == "GGUF path and extension required.")
    { d04RelativeRejected = true; }
    Assert(d04RelativeRejected && (await a.ReadAsync()).Count == deniedGgufBaseline,
        "D04 relative reviewed GGUF path denied without queue mutation");

    async Task RejectUnreviewedGguf(string rights, string origin, string label)
    {
        var rejected = false;
        try { await a.EnqueueVerifiedGgufAsync("local:denied-rights", file, size, sha, rights, origin); }
        catch (InvalidDataException ex) when
            (ex.Message == "REVIEW_REQUIRED: GGUF expected bytes/SHA-256/rights receipt.")
        { rejected = true; }
        Assert(rejected && (await a.ReadAsync()).Count == deniedGgufBaseline, label);
    }
    await RejectUnreviewedGguf(new string('r', 129), evidence,
        "D04 GGUF oversized rights reference never queued");
    await RejectUnreviewedGguf(string.Concat("owner", (char)10, "rights"), evidence,
        "D04 GGUF control characters in rights receipt never queued");
    await RejectUnreviewedGguf("reviewed", "https://token@ollama.com/library/tinyllama",
        "D04 GGUF credential-bearing license source never queued");
    await RejectUnreviewedGguf("reviewed", "https://ollama.com:444/library/tinyllama",
        "D04 GGUF nondefault HTTPS port never queued");
    // Native owner URL evidence cannot be loopback, local or fragment-backed.
    await RejectUnreviewedGguf("reviewed", "https://localhost/license",
        "D04 R5 native localhost license denied without queue mutation");
    await RejectUnreviewedGguf("reviewed", "https://127.0.0.1/license",
        "D04 R5 IPv4 loopback license denied without queue mutation");
    await RejectUnreviewedGguf("reviewed", "https://[::1]/license",
        "D04 R5 IPv6 loopback license denied without queue mutation");
    await RejectUnreviewedGguf("reviewed", "https://rights.local/license",
        "D04 R5 .local origin license denied without queue mutation");
    await RejectUnreviewedGguf("reviewed", "https://rights.internal/license",
        "D04 R5 .internal origin license denied without queue mutation");
    await RejectUnreviewedGguf("reviewed", "https://preview.localhost/license",
        "D04 R5 .localhost origin license denied without queue mutation");
    await RejectUnreviewedGguf("reviewed", "https://ollama.com/library/tinyllama#forged",
        "D04 R5 fragment evidence license denied without queue mutation");
    // Legacy records are not erased. An invalid pre-existing GGUF job must
    // fail before either atomic Running claim or explicit retry.
    var unsafeLegacyDir = Path.Combine(multiRoot, "legacy-unsafe-gguf");
    var unsafeLegacyQueue = new ModelDownloadQueueStore(unsafeLegacyDir);
    var unsafeAt = DateTimeOffset.UtcNow;
    var unsafeLegacyJob = new ModelJob(Guid.NewGuid(), ModelJobKind.GgufImport,
        "local:legacy-invalid", file, true, evidence, unsafeAt, unsafeAt,
        ExpectedLocalBytes: size, ExpectedLocalSha256: sha, RightsReceiptId: new string('r', 129));
    await File.WriteAllTextAsync(Path.Combine(unsafeLegacyDir, "p03-model-download-queue.json"),
        JsonSerializer.Serialize(new[] { unsafeLegacyJob }, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    var unsafeClaimDenied = false;
    try { await unsafeLegacyQueue.TryStartQueuedAsync(unsafeLegacyJob.Id); }
    catch (InvalidOperationException ex) when (ex.Message == "REVIEW_REQUIRED: unreviewed GGUF cannot start.")
    { unsafeClaimDenied = true; }
    Assert(unsafeClaimDenied &&
        (await unsafeLegacyQueue.ReadAsync()).Single().State == ModelJobState.Queued,
        "D04 legacy unsafe GGUF cannot be promoted to Running");
    // D04: exercise the real worker on a legacy unsafe GGUF job. No HTTP request.
    using (var legacyHttp = new HttpClient(new StalledOllamaHandler()) {
        BaseAddress = new Uri("http://127.0.0.1:11434/")
    })
    {
        var legacyAdapter = new OllamaModelAdapter(legacyHttp, unsafeLegacyDir);
        var legacyPublisher = new ModelLifecyclePublisher(new SilentP03Sink());
        var legacyWorker = new ModelDownloadQueueWorker(
            unsafeLegacyQueue, legacyAdapter, legacyPublisher);
        await legacyWorker.RunNextAsync(requestedJobId: unsafeLegacyJob.Id);
    }
    var rejectedLegacy = (await unsafeLegacyQueue.ReadAsync()).Single();
    Assert(rejectedLegacy.State == ModelJobState.Failed &&
        rejectedLegacy.Error == "GGUF_RIGHTS_REVIEW_REQUIRED" &&
        rejectedLegacy.RightsReceiptId == unsafeLegacyJob.RightsReceiptId &&
        rejectedLegacy.ModelTag == unsafeLegacyJob.ModelTag,
        "D04 unreviewed legacy GGUF worker completes safely without corrupting queue");
    var unsafeRetryDenied = false;
    try { await unsafeLegacyQueue.RetryAsync(unsafeLegacyJob.Id); }
    catch (InvalidOperationException ex) when (ex.Message == "REVIEW_REQUIRED: unreviewed GGUF cannot be retried.")
    { unsafeRetryDenied = true; }
    Assert(unsafeRetryDenied && (await unsafeLegacyQueue.ReadAsync()).Count == 1,
        "D04 legacy unsafe GGUF retry denied without data loss");
    // B04: legacy GGUF snapshots stay readable, but unsafe identity may not
    // be promoted into an active installed-model mutation after owner review.
    var unsafeGgufShapes = new (string Label, ModelJob Job)[] {
        ("mutable-tag", unsafeLegacyJob with {
            ModelTag = "local:latest", RightsReceiptId = "native-reviewed-rights" }),
        ("relative-path", unsafeLegacyJob with {
            ModelTag = "local:legacy-relative", LocalPath = "legacy-relative.gguf",
            RightsReceiptId = "native-reviewed-rights" }),
        ("wrong-extension", unsafeLegacyJob with {
            ModelTag = "local:legacy-extension", LocalPath = Path.Combine(multiRoot, "not-gguf.bin"),
            RightsReceiptId = "native-reviewed-rights" }),
        ("loopback-license", unsafeLegacyJob with {
            ModelTag = "local:legacy-loopback", LocalPath = file,
            RightsReceiptId = "native-reviewed-rights",
            LicenseSource = "https://127.0.0.1/license" }),
        ("internal-license", unsafeLegacyJob with {
            ModelTag = "local:legacy-internal", LocalPath = file,
            RightsReceiptId = "native-reviewed-rights",
            LicenseSource = "https://rights.internal/license" })
    };
    foreach (var (label, shape) in unsafeGgufShapes)
    {
        var legacyDir = Path.Combine(multiRoot, "legacy-gguf-" + label);
        var legacyStore = new ModelDownloadQueueStore(legacyDir);
        var legacy = shape with { Id = Guid.NewGuid(), State = ModelJobState.Queued };
        var queuePath = Path.Combine(legacyDir, "p03-model-download-queue.json");
        await File.WriteAllTextAsync(queuePath,
            JsonSerializer.Serialize(new[] { legacy }, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        var untouched = await File.ReadAllBytesAsync(queuePath);
        var deniedClaim = false;
        try { await legacyStore.TryStartQueuedAsync(legacy.Id); }
        catch (InvalidOperationException ex) when (ex.Message == "REVIEW_REQUIRED: unreviewed GGUF cannot start.")
        { deniedClaim = true; }
        Assert(deniedClaim &&
            (await File.ReadAllBytesAsync(queuePath)).SequenceEqual(untouched) &&
            (await legacyStore.ReadAsync()).Single().State == ModelJobState.Queued,
            "B04 legacy " + label + " GGUF claim refused without data loss");
        using (var httpGuard = new HttpClient(new StalledOllamaHandler()) {
            BaseAddress = new Uri("http://127.0.0.1:11434/")
        })
        {
            var workerGuard = new ModelDownloadQueueWorker(legacyStore,
                new OllamaModelAdapter(httpGuard, legacyDir),
                new ModelLifecyclePublisher(new SilentP03Sink()));
            await workerGuard.RunNextAsync(requestedJobId: legacy.Id);
        }
        var failedGuard = (await legacyStore.ReadAsync()).Single();
        Assert(failedGuard.State == ModelJobState.Failed &&
            failedGuard.Error == "GGUF_RIGHTS_REVIEW_REQUIRED" &&
            failedGuard.LocalPath == legacy.LocalPath,
            "B04 legacy " + label + " GGUF worker refused before HTTP");
        var deniedRetry = false;
        try { await legacyStore.RetryAsync(legacy.Id); }
        catch (InvalidOperationException ex) when (ex.Message == "REVIEW_REQUIRED: unreviewed GGUF cannot be retried.")
        { deniedRetry = true; }
        Assert(deniedRetry && (await legacyStore.ReadAsync()).Count == 1,
            "B04 legacy " + label + " GGUF retry refused");
    }
    // D04 regression: reject a stale unsafe head and actually serve the next
    // approved queued GGUF in ONE original RunNextAsync invocation, without
    // bypassing native rights, changing history, or using a real network.
    var fifoRoot = Path.Combine(multiRoot, "d04-legacy-fifo");
    var fifoStore = new ModelDownloadQueueStore(fifoRoot);
    var fifoUnsafe = unsafeLegacyJob with { Id = Guid.NewGuid() };
    await File.WriteAllTextAsync(Path.Combine(fifoRoot, "p03-model-download-queue.json"),
        JsonSerializer.Serialize(new[] { fifoUnsafe }, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    var fifoApproved = await fifoStore.EnqueueVerifiedGgufAsync(
        "local:d04-verified-next", file, size, sha, "native-verified-receipt", evidence);
    var fifoHandler = new D04RightsGgufHandler(fifoApproved.ModelTag,
        "sha256:" + new string('e', 64));
    using (var fifoClient = new HttpClient(fifoHandler) {
        BaseAddress = new Uri("http://127.0.0.1:11434/")
    })
    {
        var fifoWorker = new ModelDownloadQueueWorker(fifoStore,
            new OllamaModelAdapter(fifoClient, fifoRoot),
            new ModelLifecyclePublisher(new SilentP03Sink()));
        await fifoWorker.RunNextAsync();
    }
    var fifoAfter = await fifoStore.ReadAsync();
    Assert(fifoAfter.Count == 2 &&
        fifoAfter.Single(j => j.Id == fifoUnsafe.Id).State == ModelJobState.Failed &&
        fifoAfter.Single(j => j.Id == fifoUnsafe.Id).Error == "GGUF_RIGHTS_REVIEW_REQUIRED" &&
        fifoAfter.Single(j => j.Id == fifoApproved.Id).State == ModelJobState.Completed &&
        fifoAfter.Single(j => j.Id == fifoApproved.Id).Attempts == 1 &&
        fifoAfter.Single(j => j.Id == fifoApproved.Id).ComputedSha256 == sha &&
        fifoHandler.CreateCalls == 1 &&
        File.Exists(fifoAfter.Single(j => j.Id == fifoApproved.Id).ReceiptPath),
        "D04 native FIFO advances past legacy unreviewed head and retains real SHA receipt");
    await Task.WhenAll(Enumerable.Range(0, 10).Select(i =>
        (i % 2 == 0 ? a : b).EnqueueVerifiedGgufAsync("local:example" + i,
            file, size, sha, "synthetic-rights", evidence)));
    Assert((await new ModelDownloadQueueStore(multiRoot).ReadAsync()).Count == 11,
        "F03 concurrent separate GGUF requests cannot overwrite each other");
    var started = await a.UpdateAsync(sameJobs[0].Id, j => j with { State = ModelJobState.Running });
    Assert(started?.State == ModelJobState.Running, "F04 state persisted under queue lease");
    var restarted = new ModelDownloadQueueStore(multiRoot);
    Assert(await restarted.RecoverInterruptedAsync() == 1, "F05 interrupted job recovered");
    var retried = await Task.WhenAll(a.RetryAsync(sameJobs[0].Id), b.RetryAsync(sameJobs[0].Id));
    Assert(retried.All(x => x is not null) &&
           retried.Select(x => x!.Id).Distinct().Count() == 1,
        "F06 two concurrent retries share one child job");
    Assert((await restarted.ReadAsync()).Count == 12,
        "F07 all prior jobs retained after retry");
    // B04: durable STOP must win recovery after a real owner worker crash.
    // Running-without-STOP remains Failed (F05), but a persisted Cancelling
    // snapshot with no live execution lease must be terminal Cancelled.
    var stoppedJob = await a.EnqueueVerifiedPullAsync(model, true);
    var inFlightStop = await a.UpdateAsync(stoppedJob.Id,
        j => j with { State = ModelJobState.Running });
    Assert(inFlightStop?.State == ModelJobState.Running &&
        await b.RequestCancelAsync(stoppedJob.Id),
        "F07A durable STOP acknowledged by second owner window");
    Assert((await a.ReadAsync()).Single(x => x.Id == stoppedJob.Id).State ==
        ModelJobState.Cancelling,
        "F07B STOP intent persisted before owner crash");
    Assert(await restarted.RecoverInterruptedAsync() == 1,
        "F07C owner crash finalizes one abandoned STOP without retry");
    var persistedStop = (await new ModelDownloadQueueStore(multiRoot).ReadAsync())
        .Single(x => x.Id == stoppedJob.Id);
    Assert(persistedStop.State == ModelJobState.Cancelled &&
        persistedStop.Error is null &&
        persistedStop.Status == "Cancelled after interrupted STOP",
        "F07D durable STOP remains Cancelled and cannot become Failed");
    Assert((await restarted.ReadAsync()).Single(x => x.Id == sameJobs[0].Id).State ==
        ModelJobState.Failed,
        "F07E interrupted Running without STOP remains Failed");
}
finally { Directory.Delete(multiRoot, recursive: true); }
Console.WriteLine("P03_FINAL_QUEUE_CONCURRENCY_PASS 7/7");


 // One existing-host HTTP client; no system proxy, external redirects, or alternate host.
using (var safeClient = OllamaLoopbackHttpClientFactory.Create(new Uri("http://localhost:11434/")))
    Assert(safeClient.BaseAddress!.Host == "127.0.0.1",
        "F08 one shared loopback transport canonicalizes localhost");
foreach (var bad in new[] {
    "http://example.com:11434/", "https://localhost:11434/",
    "http://user:secret@localhost:11434/", "http://localhost:11434/api/",
    "http://localhost:11434/?redirect=1" })
{
    try {
        OllamaLoopbackHttpClientFactory.ValidateAndCanonicalize(new Uri(bad));
        throw new Exception("FAIL F09 disallowed host/URL " + bad);
    }
    catch (InvalidOperationException) { /* expected */ }
}
Assert(true, "F09 all remote/proxy-ambiguous endpoint shapes denied");
Console.WriteLine("P03_FINAL_TRANSPORT_POLICY_PASS 2/2");

 // Owner3 atomic-claim regression: only one process starts a given model job.
var atomicRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_CLAIM_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(atomicRoot);
try
{
    var left = new ModelDownloadQueueStore(atomicRoot);
    var right = new ModelDownloadQueueStore(atomicRoot);
    var approved = ModelCatalog.Get("tinyllama") with {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:1.1b", Version = "synthetic-only", License = "synthetic-license",
        ArtifactBytes = 100, RequiredDiskBytes = 200, RecommendedRamBytes = 300,
        ExpectedSha256 = new string('b', 64), ExpectedManifestDigestSha256 = new string('a', 64),
        ImmutableRevision = "sha256:" + new string('a', 64), CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri("https://ollama.com/library/tinyllama"),
        CompatibilityEvidenceUri = new Uri("https://ollama.com/library/tinyllama"), ReviewedRightsReceiptId = "rights-fixture"
    };
    var ticket = await left.EnqueueVerifiedPullAsync(approved, true);
    var d04File = Path.Combine(atomicRoot, "cross-kind.gguf");
    await File.WriteAllBytesAsync(d04File, Encoding.ASCII.GetBytes("GGUF synthetic cross-kind"));
    var d04Bytes = await File.ReadAllBytesAsync(d04File);
    var d04Digest = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(d04Bytes)).ToLowerInvariant();
    var d04ImportDenied = false;
    try { await right.EnqueueVerifiedGgufAsync("TINYLLAMA:1.1b", d04File,
        d04Bytes.Length, d04Digest, "rights-fixture", approved.LicenseEvidenceUri!.ToString()); }
    catch (InvalidOperationException ex) when (ex.Message == "P03_ACTIVE_MODEL_TAG_CONFLICT_HOLD")
    { d04ImportDenied = true; }
    Assert(d04ImportDenied && (await right.ReadAsync()).Count == 1,
        "D04G GGUF cannot overwrite active reviewed pull or mutate queue");
    var d04MixedStore = new ModelDownloadQueueStore(Path.Combine(atomicRoot, "cross-kind-reverse"));
    await d04MixedStore.EnqueueVerifiedGgufAsync("tinyllama:1.1b", d04File,
        d04Bytes.Length, d04Digest, "rights-fixture", approved.LicenseEvidenceUri!.ToString());
    var d04PullDenied = false;
    try { await d04MixedStore.EnqueueVerifiedPullAsync(approved, true); }
    catch (InvalidOperationException ex) when (ex.Message == "P03_ACTIVE_PULL_REVIEW_CHANGED_HOLD")
    { d04PullDenied = true; }
    Assert(d04PullDenied && (await d04MixedStore.ReadAsync()).Count == 1,
        "D04H reviewed pull cannot replace active GGUF under other job ID");
    Assert(ticket.RightsReceiptId == approved.ReviewedRightsReceiptId,
        "F09A queue preserves approved rights evidence");
    // A live pull can be re-used ONLY with the same exact owner authority.
    // Rights revocation or review drift must not ACK an old queued/running job.
    var sameApproved = await right.EnqueueVerifiedPullAsync(approved, true);
    Assert(sameApproved.Id == ticket.Id, "F09C same owner review shares one active transfer");
    async Task ExpectReviewDriftHold(ModelCatalogEntry changed, string name)
    {
        var rejected = false;
        try { await right.EnqueueVerifiedPullAsync(changed, true); }
        catch (InvalidOperationException ex) when (ex.Message == "P03_ACTIVE_PULL_REVIEW_CHANGED_HOLD")
        { rejected = true; }
        Assert(rejected, name);
    }
    await ExpectReviewDriftHold(approved with { ReviewedRightsReceiptId = "rights-revoked" },
        "F09D active pull rejects changed rights receipt");
    await ExpectReviewDriftHold(approved with {
        LicenseEvidenceUri = new Uri("https://ollama.com/library/tinyllama?owner-review=changed") },
        "F09E active pull rejects changed licensed origin");
    await ExpectReviewDriftHold(approved with {
        ExpectedManifestDigestSha256 = new string('c', 64) },
        "F09F active pull rejects changed manifest digest");
    await ExpectReviewDriftHold(approved with {
        ImmutableRevision = "sha256:" + new string('c', 64) },
        "F09G active pull rejects changed immutable revision");
    await ExpectReviewDriftHold(approved with { ExactTag = "TinyLlama:1.1b" },
        "F09H active pull rejects case-colliding owner tag");
    Assert((await right.ReadAsync()).Count == 1,
        "F09I denied review drift makes no duplicate persisted queue job");

    // Original RetryAsync must honor the SAME owner-reviewed, case-exact
    // active-tag rules as EnqueueVerifiedPullAsync, including persisted rights.
    var retryRoot = Path.Combine(atomicRoot, "retry-authority");
    var retryQueue = new ModelDownloadQueueStore(retryRoot);
    var oldReview = approved with { ExactTag = "tinyllama:retry-reviewed",
        ReviewedRightsReceiptId = "rights-previous" };
    var failedReview = await retryQueue.EnqueueVerifiedPullAsync(oldReview, true);
    await retryQueue.UpdateAsync(failedReview.Id, j => j with { State = ModelJobState.Failed });
    var newReview = await retryQueue.EnqueueVerifiedPullAsync(
        oldReview with { ReviewedRightsReceiptId = "rights-current" }, true);
    var oldRetryDenied = false;
    try { await retryQueue.RetryAsync(failedReview.Id); }
    catch (InvalidOperationException ex) when (ex.Message == "P03_RETRY_ACTIVE_PULL_REVIEW_CHANGED_HOLD")
    { oldRetryDenied = true; }
    Assert(oldRetryDenied, "F09J obsolete rights cannot retry beside new approved pull");
    var reviewJobs = await retryQueue.ReadAsync();
    Assert(reviewJobs.Count == 2 &&
        reviewJobs.Single(j => j.Id == newReview.Id).RightsReceiptId == "rights-current" &&
        reviewJobs.Count(j => j.State == ModelJobState.Queued) == 1,
        "F09K denied retry leaves active approved queue and rights intact");
    var legacyQueue = new ModelDownloadQueueStore(Path.Combine(atomicRoot, "retry-legacy"));
    var legacyJob = await legacyQueue.EnqueueVerifiedPullAsync(
        approved with { ExactTag = "tinyllama:legacy-retry" }, true);
    await legacyQueue.UpdateAsync(legacyJob.Id, j => j with {
        State = ModelJobState.Failed, RightsReceiptId = null });
    var legacyRetryDenied = false;
    try { await legacyQueue.RetryAsync(legacyJob.Id); }
    catch (InvalidOperationException ex) when (
        ex.Message == "REVIEW_REQUIRED: legacy/unreviewed pull cannot be retried")
    { legacyRetryDenied = true; }
    Assert(legacyRetryDenied && (await legacyQueue.ReadAsync()).Count == 1,
        "F09L legacy pull lacking native rights cannot manufacture a retry");
    var sameRetryQueue = new ModelDownloadQueueStore(Path.Combine(atomicRoot, "retry-idempotent"));
    var sameParent = await sameRetryQueue.EnqueueVerifiedPullAsync(
        approved with { ExactTag = "tinyllama:retry-identical" }, true);
    await sameRetryQueue.UpdateAsync(sameParent.Id, j => j with { State = ModelJobState.Failed });
    var sameChild = await sameRetryQueue.RetryAsync(sameParent.Id);
    var sameChildAgain = await sameRetryQueue.RetryAsync(sameParent.Id);
    Assert(sameChild is not null && sameChildAgain?.Id == sameChild.Id &&
        (await sameRetryQueue.ReadAsync()).Count == 2,
        "F09M original exact-rights retry stays idempotent across instances");
    // D04: a preexisting GGUF retry must retain identical approved native rights
    // and expected real weight SHA before returning the same retry jobId.
    var ggufRetryRoot = Path.Combine(atomicRoot, "retry-gguf-native-identity");
    var ggufRetryQueue = new ModelDownloadQueueStore(ggufRetryRoot);
    var ggufParent = await ggufRetryQueue.EnqueueVerifiedGgufAsync("tinyllama:gguf-retry-pin",
        d04File, d04Bytes.Length, d04Digest, "rights-fixture",
        approved.LicenseEvidenceUri!.ToString());
    await ggufRetryQueue.UpdateAsync(ggufParent.Id, j => j with { State = ModelJobState.Failed });
    var ggufChild = await ggufRetryQueue.RetryAsync(ggufParent.Id);
    Assert(ggufChild is not null && ggufChild.RetryOfJobId == ggufParent.Id,
        "D04 genuine reviewed GGUF retry remains idempotent");
    await ggufRetryQueue.UpdateAsync(ggufChild!.Id, j => j with { RightsReceiptId = "rights-swapped" });
    var ggufQueueFile = Path.Combine(ggufRetryRoot, "p03-model-download-queue.json");
    var ggufBeforeRights = await File.ReadAllBytesAsync(ggufQueueFile);
    var ggufRightsHeld = false;
    try { await ggufRetryQueue.RetryAsync(ggufParent.Id); }
    catch (InvalidOperationException ex) when (ex.Message ==
        "P03_RETRY_ACTIVE_ARTIFACT_REVIEW_CHANGED_HOLD") { ggufRightsHeld = true; }
    Assert(ggufRightsHeld && ggufBeforeRights.SequenceEqual(await File.ReadAllBytesAsync(ggufQueueFile)),
        "D04 modified GGUF retry rights cannot ACK or alter queue");
    await ggufRetryQueue.UpdateAsync(ggufChild.Id, j => j with {
        RightsReceiptId = "rights-fixture", ExpectedLocalSha256 = new string('c', 64) });
    var ggufBeforeSha = await File.ReadAllBytesAsync(ggufQueueFile);
    var ggufShaHeld = false;
    try { await ggufRetryQueue.RetryAsync(ggufParent.Id); }
    catch (InvalidOperationException ex) when (ex.Message ==
        "P03_RETRY_ACTIVE_ARTIFACT_REVIEW_CHANGED_HOLD") { ggufShaHeld = true; }
    Assert(ggufShaHeld && ggufBeforeSha.SequenceEqual(await File.ReadAllBytesAsync(ggufQueueFile)),
        "D04 modified GGUF weight SHA cannot ACK or alter queue");
    Console.WriteLine("P03_RETRY_AUTHORITY_REGRESSION_PASS 4/4");
    // Legacy records remain readable but floating revisions cannot become
    // new native transfers or manufacture retry rights.
    var d04OldDir = Path.Combine(atomicRoot, "legacy-immutable-pull");
    var d04OldStore = new ModelDownloadQueueStore(d04OldDir);
    var d04Old = ticket with { Id = Guid.NewGuid(),
        ModelTag = "tinyllama:legacy-float", ImmutableRevision = "rolling-branch" };
    var d04OldPath = Path.Combine(d04OldDir, "p03-model-download-queue.json");
    await File.WriteAllTextAsync(d04OldPath, JsonSerializer.Serialize(new[] { d04Old },
        new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    var d04BeforeClaim = await File.ReadAllBytesAsync(d04OldPath);
    var d04ClaimHeld = false;
    try { await d04OldStore.TryStartQueuedAsync(d04Old.Id); }
    catch (InvalidOperationException ex) when (ex.Message ==
        "REVIEW_REQUIRED: unpinned Pull cannot start.") { d04ClaimHeld = true; }
    Assert(d04ClaimHeld && (await d04OldStore.ReadAsync()).Single().State == ModelJobState.Queued &&
        d04BeforeClaim.SequenceEqual(await File.ReadAllBytesAsync(d04OldPath)),
        "D04 legacy floating revision cannot claim or alter source queue");
    var d04OldFailed = d04Old with { State = ModelJobState.Failed };
    await File.WriteAllTextAsync(d04OldPath, JsonSerializer.Serialize(new[] { d04OldFailed },
        new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    var d04BeforeRetry = await File.ReadAllBytesAsync(d04OldPath);
    var d04RetryHeld = false;
    try { await d04OldStore.RetryAsync(d04OldFailed.Id); }
    catch (InvalidOperationException ex) when (ex.Message ==
        "REVIEW_REQUIRED: legacy/unreviewed pull cannot be retried.") { d04RetryHeld = true; }
    Assert(d04RetryHeld && (await d04OldStore.ReadAsync()).Count == 1 &&
        d04BeforeRetry.SequenceEqual(await File.ReadAllBytesAsync(d04OldPath)),
        "D04 legacy floating revision cannot retry or erase history");
    var claims = await Task.WhenAll(Enumerable.Range(0, 24).Select(i =>
        (i % 2 == 0 ? left : right).TryStartQueuedAsync(ticket.Id)));
    Assert(claims.Count(x => x is not null) == 1, "F10 only one process acquires model job");
    var persistedClaim = (await right.ReadAsync()).Single();
    Assert(persistedClaim.RightsReceiptId == approved.ReviewedRightsReceiptId,
        "F09B persisted queue readback preserves rights evidence");
    Assert(persistedClaim.State == ModelJobState.Running && persistedClaim.Attempts == 1,
        "F11 exactly one attempt persisted");
    async Task RequireActiveRestoreHoldAsync(string label)
    {
        var queueFile = Path.Combine(atomicRoot, "p03-model-download-queue.json");
        var backupFile = queueFile + ".bak";
        var currentBefore = await File.ReadAllBytesAsync(queueFile);
        var backupBefore = await File.ReadAllBytesAsync(backupFile);
        var held = false;
        try { await right.RestoreBackupAsync(explicitlyConfirmed: true); }
        catch (InvalidOperationException ex)
            when (ex.Message == "P03_QUEUE_ACTIVE_RESTORE_HOLD") { held = true; }
        Assert(held &&
            currentBefore.SequenceEqual(await File.ReadAllBytesAsync(queueFile)) &&
            backupBefore.SequenceEqual(await File.ReadAllBytesAsync(backupFile)) &&
            !Directory.EnumerateFiles(atomicRoot,
                "p03-model-download-queue.json.pre_restore.*").Any(),
            label);
    }
    await RequireActiveRestoreHoldAsync(
        "B04R1 confirmed rollback cannot replace a Running owner's queue");
    var toCancel = await right.EnqueueVerifiedPullAsync(approved with {
        ExactTag = "tinyllama:test-cancel", ImmutableRevision = "sha256:" + new string('b', 64),
        ExpectedManifestDigestSha256 = new string('b', 64) }, true);
    Assert(await right.CancelQueuedAsync(toCancel.Id), "F12 queue STOP persisted");
    Assert(await left.TryStartQueuedAsync(toCancel.Id) is null,
        "F13 cancelled queued job can never be claimed");
    Assert(await right.RequestCancelAsync(ticket.Id), "F14 remote STOP accepted");
    Assert((await left.ReadAsync()).Single(j => j.Id == ticket.Id).State ==
        ModelJobState.Cancelling, "F15 stop state visible to another NOX window");
    await RequireActiveRestoreHoldAsync(
        "B04R2 confirmed rollback cannot erase a durable active STOP");
    Assert(await left.RequestCancelAsync(ticket.Id), "F16 second STOP is idempotent");
    Assert(await right.TryStartQueuedAsync(ticket.Id) is null,
        "F17 remote STOP cannot restart an active job");
}
finally { Directory.Delete(atomicRoot, recursive: true); }
Console.WriteLine("P03_ATOMIC_CLAIM_TEST_PASS 4/4");

 // F18-F21: the ACTUAL worker must observe a STOP from another NOX window.
 // No real model or network request is made; the fake Pull stream waits for
 // cancellation, so only an actual worker STOP can complete this scenario.
var stopRoot = Path.Combine(Path.GetTempPath(), "NOX_P03_STOP_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(stopRoot);
try
{
    var sourceQueue = new ModelDownloadQueueStore(stopRoot);
    var remoteQueue = new ModelDownloadQueueStore(stopRoot);
    var reviewed = ModelCatalog.Get("tinyllama") with {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:worker-stop", Version = "synthetic-fixture",
        License = "synthetic-license", ArtifactBytes = 100,
        RequiredDiskBytes = 200, RecommendedRamBytes = 300,
        ExpectedSha256 = new string('b', 64),
        ExpectedManifestDigestSha256 = new string('a', 64),
        ImmutableRevision = "sha256:" + new string('a', 64),
        CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri("https://ollama.com/library/tinyllama"),
        CompatibilityEvidenceUri = new Uri("https://ollama.com/library/tinyllama"), ReviewedRightsReceiptId = "rights-fixture"
    };
    var waitingJob = await sourceQueue.EnqueueVerifiedPullAsync(reviewed, true);
    using var loopback = new HttpClient(new StalledOllamaHandler()) {
        BaseAddress = new Uri("http://127.0.0.1:11434/")
    };
    var adapter = new OllamaModelAdapter(loopback, stopRoot);
    var publisher = new ModelLifecyclePublisher(new SilentP03Sink());
    var owningWorker = new ModelDownloadQueueWorker(sourceQueue, adapter, publisher);
    var secondWindow = new ModelDownloadQueueWorker(remoteQueue, adapter, publisher);
    var operation = owningWorker.RunNextAsync();
    var observedStart = false;
    for (var i = 0; i < 150; i++)
    {
        var saved = (await remoteQueue.ReadAsync()).Single();
        if (saved.State == ModelJobState.Running)
        {
            observedStart = true;
            break;
        }
        await Task.Delay(20);
    }
    Assert(observedStart, "F18 actual worker claimed job before cross-window STOP");
    Assert(await remoteQueue.RecoverInterruptedAsync() == 0,
        "F22 second NOX window cannot recover a live working job");
    Assert((await remoteQueue.ReadAsync()).Single().State == ModelJobState.Running,
        "F23 active worker state survives another window startup");
    var remoteStopAccepted = await secondWindow.CancelAsync(waitingJob.Id);
    var stopSnapshot = (await remoteQueue.ReadAsync()).Single();
    Assert(remoteStopAccepted,
        "F19 second-window STOP accepted; state=" + stopSnapshot.State +
        " error=" + stopSnapshot.Error);
    await operation.WaitAsync(TimeSpan.FromSeconds(8));
    var finished = (await remoteQueue.ReadAsync()).Single();
    Assert(finished.State == ModelJobState.Cancelled,
        "F20 worker cancelled stalled stream through shared STOP");
    Assert(!File.Exists(adapter.ReceiptPathFor(waitingJob.Id)),
        "F21 canceled job cannot forge an installed-model receipt");
}
finally { Directory.Delete(stopRoot, recursive: true); }
Console.WriteLine("P03_SHARED_WORKER_STOP_PASS 4/4");

// D04 owner-rights regression: exercise the ORIGINAL GGUF adapter end-to-end
// against an in-memory loopback API, without downloading any model weights.
// B04 R5: a native P04 rights receipt cannot be silently reinterpreted
// relative to the OneHost working directory. Both original reviewed paths
// must be fully qualified BEFORE any queue mutation.
var b04MergedRoot = Path.Combine(Path.GetTempPath(), "NOX_B04_P04_MERGE_PATH_" + Guid.NewGuid().ToString("N"));
try
{
    var mergedQueue = new ModelDownloadQueueStore(b04MergedRoot);
    var approvedMerge = new P04MergedImportApproval(
        "relative-merged", new string('a', 64), new string('b', 64),
        "relative-training.json", new string('c', 64),
        "rights-attestation", new string('d', 64),
        "https://example.com/reviewed-license", "native-approval", true);
    var mergeAbsoluteDir = Path.Combine(Path.GetTempPath(), "uncreated-b04-merged");
    var mergeAbsoluteReceipt = Path.Combine(Path.GetTempPath(), "uncreated-b04-training.json");
    foreach (var bad in new[]
    {
        approvedMerge with { TrainingReceiptPath = mergeAbsoluteReceipt },
        approvedMerge with { Directory = mergeAbsoluteDir },
        approvedMerge with { Directory = "C:drive-relative", TrainingReceiptPath = mergeAbsoluteReceipt }
    })
    {
        var originalCount = (await mergedQueue.ReadAsync()).Count;
        var held = false;
        try { await mergedQueue.EnqueueVerifiedMergedAsync(bad, nativeConsent: true); }
        catch (InvalidDataException ex) when (ex.Message == "P03_P04_MERGE_OWNER_ABSOLUTE_PATH_HOLD")
        { held = true; }
        Assert(held && (await mergedQueue.ReadAsync()).Count == originalCount,
            "B04 P04 native owner refuses relative merge/training receipt paths without queue mutation");
        // Test the ORIGINAL public adapter, which reuses the common validation
        // gate even for legacy persisted jobs and direct adapter entry.
        // No network or weights are used: validation must fail before Ollama I/O.
        using var b04Client = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:11434/") };
        var b04Adapter = new OllamaModelAdapter(b04Client, b04MergedRoot);
        var b04Id = Guid.NewGuid();
        var b04Job = new ModelJob(b04Id, ModelJobKind.SafetensorsImport,
            "nox-forge-" + bad.MergedPayloadSha256[..12] + ":" + b04Id.ToString("N"),
            bad.Directory, true, bad.LicenseSource, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
            ExpectedLocalSha256: bad.MergedPayloadSha256, MergedImport: bad);
        var directHeld = false;
        try
        {
            await b04Adapter.ImportMergedSafetensorsAsync(b04Job,
                (update, token) => ValueTask.CompletedTask, CancellationToken.None);
        }
        catch (InvalidDataException ex) when (ex.Message == "P03_P04_MERGE_OWNER_ABSOLUTE_PATH_HOLD")
        { directHeld = true; }
        Assert(directHeld, "B04 P04 original adapter refuses CWD-dependent owner paths");
    }

    // D04 R5: require public HTTPS merged rights evidence before any local
    // state mutation or Ollama I/O. No model weights are downloaded here.
    var d04Public = approvedMerge with {
        Directory = Path.Combine(b04MergedRoot, "d04-new-nonexistent-merged"),
        TrainingReceiptPath = Path.Combine(b04MergedRoot, "d04-new-nonexistent-training.json")
    };
    foreach (var badEvidence in new[] {
        "https://localhost/license", "https://127.0.0.1/license",
        "https://[::1]/license", "https://private.local/license",
        "https://private.internal/license", "https://sub.localhost/license",
        "https://example.com:444/license", "https://example.com/license#fake"
    })
    {
        var unreviewed = d04Public with { LicenseSource = badEvidence };
        var before = (await mergedQueue.ReadAsync()).Count;
        var enqueueDenied = false;
        try { await mergedQueue.EnqueueVerifiedMergedAsync(unreviewed, nativeConsent: true); }
        catch (InvalidDataException ex) when (ex.Message == "P03_P04_NATIVE_RIGHTS_APPROVAL_REQUIRED")
        { enqueueDenied = true; }
        Assert(enqueueDenied && (await mergedQueue.ReadAsync()).Count == before,
            "D04 P04 queue denies local/private license without mutation: " + badEvidence);
        var candidateId = Guid.NewGuid();
        var candidate = new ModelJob(candidateId, ModelJobKind.SafetensorsImport,
            "nox-forge-" + unreviewed.MergedPayloadSha256[..12] + ":" + candidateId.ToString("N"),
            unreviewed.Directory, true, unreviewed.LicenseSource,
            DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, ExpectedLocalBytes: 123,
            ExpectedLocalSha256: unreviewed.MergedPayloadSha256,
            RightsReceiptId: unreviewed.RightsAttestationId, MergedImport: unreviewed);
        using var localHttp = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:11434/") };
        var native = new OllamaModelAdapter(localHttp, b04MergedRoot);
        var directDenied = false;
        try { await native.ImportMergedSafetensorsAsync(candidate,
            (evt, token) => ValueTask.CompletedTask, CancellationToken.None); }
        catch (SafetensorsImportHold ex) when (ex.Code == "P03_MERGED_REVIEW_REQUIRED")
        { directDenied = true; }
        Assert(directDenied, "D04 direct adapter denies private P04 evidence before HTTP: " + badEvidence);
    }
    var publicToReceipt = false;
    try { await mergedQueue.EnqueueVerifiedMergedAsync(d04Public, nativeConsent: true); }
    catch (InvalidDataException ex) when (ex.Message == "P03_MERGED_DIRECTORY_MISSING")
    { publicToReceipt = true; }
    Assert(publicToReceipt, "D04 public HTTPS passes only to original P04 receipt/filesystem gate");

    // D04 R5: a legacy P04 job can have syntactically valid weight SHA and
    // NativeRightsVerified=true while its training-receipt path remains relative.
    // Preserve the old snapshot, refuse atomic Running/retry/direct native I/O,
    // and let the original FIFO worker fail only that unreviewed item.
    var legacyMergeApproval = approvedMerge with {
        Directory = mergeAbsoluteDir, TrainingReceiptPath = "relative-training.json"
    };
    var legacyMergeId = Guid.NewGuid();
    var legacyMergeAt = DateTimeOffset.UtcNow;
    var legacyMergeJob = new ModelJob(legacyMergeId, ModelJobKind.SafetensorsImport,
        "nox-forge-" + legacyMergeApproval.MergedPayloadSha256[..12] + ":" + legacyMergeId.ToString("N"),
        legacyMergeApproval.Directory, true, legacyMergeApproval.LicenseSource,
        legacyMergeAt, legacyMergeAt, ExpectedLocalBytes: 123,
        ExpectedLocalSha256: legacyMergeApproval.MergedPayloadSha256,
        RightsReceiptId: legacyMergeApproval.RightsAttestationId,
        MergedImport: legacyMergeApproval);
    var legacyMergeSnapshot = Path.Combine(b04MergedRoot, "p03-model-download-queue.json");
    await File.WriteAllTextAsync(legacyMergeSnapshot,
        JsonSerializer.Serialize(new[] { legacyMergeJob },
            new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    var legacyMergeBytes = await File.ReadAllBytesAsync(legacyMergeSnapshot);
    var legacyClaimDenied = false;
    try { await mergedQueue.TryStartQueuedAsync(legacyMergeId); }
    catch (InvalidOperationException ex) when
        (ex.Message == "REVIEW_REQUIRED: unreviewed merged import cannot start.")
    { legacyClaimDenied = true; }
    Assert(legacyClaimDenied &&
        (await File.ReadAllBytesAsync(legacyMergeSnapshot)).SequenceEqual(legacyMergeBytes),
        "D04 R5 legacy merged owner path rejected before Running without snapshot mutation");
    using (var mergedHttp = new HttpClient(new StalledOllamaHandler()) {
        BaseAddress = new Uri("http://127.0.0.1:11434/")
    })
    {
        var mergedAdapter = new OllamaModelAdapter(mergedHttp, b04MergedRoot);
        var directDenied = false;
        try { await mergedAdapter.ImportMergedSafetensorsAsync(legacyMergeJob,
            (evt, token) => ValueTask.CompletedTask, default); }
        catch (SafetensorsImportHold ex) when (ex.Code == "P03_MERGED_REVIEW_REQUIRED")
        { directDenied = true; }
        Assert(directDenied, "D04 R5 direct merged adapter refuses stale P04 authority before HTTP");
        var mergedWorker = new ModelDownloadQueueWorker(mergedQueue, mergedAdapter,
            new ModelLifecyclePublisher(new SilentP03Sink()));
        await mergedWorker.RunNextAsync(requestedJobId: legacyMergeId);
    }
    var legacyRejected = (await mergedQueue.ReadAsync()).Single();
    Assert(legacyRejected.State == ModelJobState.Failed &&
        legacyRejected.Error == "MERGED_RIGHTS_REVIEW_REQUIRED" &&
        legacyRejected.MergedImport == legacyMergeApproval,
        "D04 R5 worker preserves rejected merged job and native provenance");
    var legacyMergeRetryDenied = false;
    try { await mergedQueue.RetryAsync(legacyMergeId); }
    catch (InvalidOperationException ex) when
        (ex.Message == "REVIEW_REQUIRED: unreviewed merged import cannot be retried.")
    { legacyMergeRetryDenied = true; }
    Assert(legacyMergeRetryDenied && (await mergedQueue.ReadAsync()).Count == 1,
        "D04 R5 merged retry cannot reuse invalid P04 owner approval");
}
finally { if (Directory.Exists(b04MergedRoot)) Directory.Delete(b04MergedRoot, recursive: true); }

var d04RightsDir = Path.Combine(Path.GetTempPath(), "NOX_P03_GGUF_RIGHTS_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(d04RightsDir);
try
{
    var payload = Encoding.ASCII.GetBytes("GGUF-owner-rights-fixture");
    var path = Path.Combine(d04RightsDir, "owner-fixture.gguf");
    await File.WriteAllBytesAsync(path, payload);
    var sha = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(payload)).ToLowerInvariant();
    var now = DateTimeOffset.UtcNow;
    var job = new ModelJob(Guid.NewGuid(), ModelJobKind.GgufImport, "tinyllama:gguf-rights-fixture",
        path, true, "https://ollama.com/library/tinyllama", now, now,
        ExpectedLocalBytes: payload.LongLength, ExpectedLocalSha256: sha,
        RightsReceiptId: "owner-reviewed-gguf-rights-fixture");
    var ggufHandler = new D04RightsGgufHandler(job.ModelTag, new string('d', 64));
    using var http = new HttpClient(ggufHandler) {
        BaseAddress = new Uri("http://127.0.0.1:11434/")
    };
    var adapter = new OllamaModelAdapter(http, d04RightsDir);
    async Task MustHoldUnreviewed(ModelJob denied, bool pull, string label)
    {
        try
        {
            if (pull) await adapter.PullAsync(denied,
                (evt, token) => ValueTask.CompletedTask, default);
            else await adapter.ImportGgufAsync(denied,
                (evt, token) => ValueTask.CompletedTask, default);
        }
        catch (InvalidDataException) { Assert(true, label); return; }
        throw new Exception("FAIL " + label);
    }
    await MustHoldUnreviewed(job with { LicenseAcknowledged = false }, false,
        "D04 GGUF direct adapter refuses unacknowledged license before Ollama");
    await MustHoldUnreviewed(job with { RightsReceiptId = new string('x', 129) }, false,
        "D04 GGUF direct adapter refuses oversized rights reference");
    await MustHoldUnreviewed(job with { ModelTag = "tinyllama:latest" }, false,
        "B04 GGUF direct adapter rejects mutable latest before Ollama");
    await MustHoldUnreviewed(job with { LocalPath = "relative.gguf" }, false,
        "B04 GGUF direct adapter rejects relative file before Ollama");
    await MustHoldUnreviewed(job with { LicenseSource = "https://127.0.0.1/license" }, false,
        "D04 R5 direct adapter blocks loopback license");
    await MustHoldUnreviewed(job with { LicenseSource = "https://rights.internal/license" }, false,
        "D04 R5 direct adapter blocks internal license");
    var pullWithoutConsent = job with { Kind = ModelJobKind.OllamaPull,
        ExpectedOllamaDigest = new string('d', 64), ImmutableRevision = "sha256:" + new string('d', 64),
        LicenseAcknowledged = false };
    await MustHoldUnreviewed(pullWithoutConsent, true,
        "D04 Pull direct adapter refuses unacknowledged license before Ollama");
    // B04: immutable remote-review consent never grants local-tag overwrite.
    var b04ReviewedPull = pullWithoutConsent with { LicenseAcknowledged = true };
    var d04Floating = b04ReviewedPull with { ImmutableRevision = "rolling-branch" };
    var d04TagsBefore = ggufHandler.TagsChecks;
    var d04DirectHeld = false;
    try { await adapter.PullAsync(d04Floating,
        (evt, token) => ValueTask.CompletedTask, default); }
    catch (InvalidDataException ex) when (ex.Message.StartsWith("REVIEW_REQUIRED:", StringComparison.Ordinal))
    { d04DirectHeld = true; }
    Assert(d04DirectHeld && ggufHandler.TagsChecks == d04TagsBefore,
        "D04 direct Ollama Pull refuses floating revision before IO");
    async Task B04RefusePullAsync(string expected, string label)
    {
        try { await adapter.PullAsync(b04ReviewedPull,
            (evt, token) => ValueTask.CompletedTask, default); }
        catch (InvalidDataException ex) when (ex.Message == expected)
        { Assert(true, label); return; }
        throw new Exception("FAIL " + label);
    }
    ggufHandler.ExistingTag = true;
    await B04RefusePullAsync("P03_PULL_EXISTING_TAG_NO_LOSS_HOLD",
        "B04 pinned Pull refuses to replace installed owner's tag");
    ggufHandler.ExistingTag = false;
    ggufHandler.FailTagsLookup = true;
    await B04RefusePullAsync("OLLAMA_TAGS_LOOKUP_FAILED_HOLD",
        "B04 provider-offline tag lookup cannot authorize a Pull");
    ggufHandler.FailTagsLookup = false;

    async Task RefuseUnsafeExisting(string expected, string label)
    {
        try { await adapter.ImportGgufAsync(job, (evt, token) => ValueTask.CompletedTask, default); }
        catch (InvalidDataException ex) when (ex.Message == expected) { Assert(true, label); return; }
        throw new Exception("FAIL " + label);
    }
    ggufHandler.ExistingTag = true;
    await RefuseUnsafeExisting("P03_GGUF_EXISTING_TAG_NO_LOSS_HOLD",
        "D04 GGUF cannot replace already installed model");
    Assert(ggufHandler.CreateCalls == 0, "D04 existing model rejected before api/create");
    ggufHandler.ExistingTag = false;
    ggufHandler.FailTagsLookup = true;
    await RefuseUnsafeExisting("OLLAMA_TAGS_LOOKUP_FAILED_HOLD",
        "D04 unavailable Ollama tags cannot be treated as absent");
    ggufHandler.FailTagsLookup = false;
    ggufHandler.TagsChecks = 0;
    ggufHandler.AppearOnSecondTagsCheck = true;
    await RefuseUnsafeExisting("P03_GGUF_EXISTING_TAG_NO_LOSS_HOLD",
        "D04 competing owner tag detected before api/create");
    Assert(ggufHandler.CreateCalls == 0, "D04 second read prevents replacement");
    ggufHandler.AppearOnSecondTagsCheck = false;
    ggufHandler.TagsChecks = 0;
    var result = await adapter.ImportGgufAsync(job,
        (evt, token) => ValueTask.CompletedTask, default);
    var receiptPath = adapter.ReceiptPathFor(job.Id);
    var saved = JsonSerializer.Deserialize<ModelInstallReceipt>(await File.ReadAllTextAsync(receiptPath),
        new JsonSerializerOptions(JsonSerializerDefaults.Web));
    Assert(saved is not null && saved.RightsAttestationId == job.RightsReceiptId &&
        saved.LocalSha256 == sha && result.Sha256 == sha &&
        result.Bytes == payload.LongLength && saved.Operation == "gguf-import",
        "D04 original GGUF success receipt binds actual SHA and native rights");
    await ModelLocalAttestation.VerifyReceiptAsync(receiptPath, saved!, default);
    try
    {
        await ModelLocalAttestation.VerifyReceiptAsync(receiptPath,
            saved! with { RightsAttestationId = "forged-review" }, default);
        throw new Exception("FAIL D04 forged rights unexpectedly match receipt");
    }
    catch (InvalidDataException)
    {
        Assert(true, "D04 owner rights cannot be substituted during receipt readback");
    }
    // B04 R5: an attacker-edited installed receipt with two case-aliased
    // digest keys must never pass last-wins Web JSON deserialization.
    var originalReceiptJson = await File.ReadAllTextAsync(receiptPath);
    const string digestKey = "\"ollamaDigest\":";
    Assert(originalReceiptJson.Contains(digestKey, StringComparison.Ordinal),
        "B04 original GGUF receipt has a manifest digest field");
    var forgedDuplicateReceipt = originalReceiptJson.Replace(digestKey,
        "\"OllamaDigest\":\"sha256:" + new string('f', 64) + "\"," + digestKey,
        StringComparison.Ordinal);
    await File.WriteAllTextAsync(receiptPath, forgedDuplicateReceipt);
    var ambiguousReceiptHeld = false;
    try { await ModelLocalAttestation.VerifyReceiptAsync(receiptPath, saved!, default); }
    catch (InvalidDataException ex) when (ex.Message == "INSTALL_RECEIPT_DUPLICATE_FIELD_HOLD")
    { ambiguousReceiptHeld = true; }
    Assert(ambiguousReceiptHeld, "B04 duplicate installed Ollama manifest identity denied");
    await File.WriteAllTextAsync(receiptPath, originalReceiptJson);
    await ModelLocalAttestation.VerifyReceiptAsync(receiptPath, saved!, default);
    Assert(true, "B04 original immutable receipt still verifies after negative fixture");
}
finally { Directory.Delete(d04RightsDir, recursive: true); }


 // D04: native STOP already pending on an active retry cannot be re-ACKed.
 // No Ollama network traffic, model downloads, or user data in these tests.
var d04RetryRoot = Path.Combine(Path.GetTempPath(), "NOX_D04_STOP_RETRY_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(d04RetryRoot);
try
{
    var d04Queue = new ModelDownloadQueueStore(d04RetryRoot);
    async Task AssertStopPendingRetryAsync(ModelJob failed, string label)
    {
        var retry = await d04Queue.RetryAsync(failed.Id);
        Assert(retry is not null && retry.State == ModelJobState.Queued, label + " queued");
        Assert(await d04Queue.TryStartQueuedAsync(retry!.Id) is not null, label + " claimed");
        Assert(await d04Queue.RequestCancelAsync(retry.Id), label + " STOP persisted");
        var before = (await d04Queue.ReadAsync()).Select(j => j.Id).ToArray();
        try
        {
            await d04Queue.RetryAsync(failed.Id);
            throw new Exception("FAIL " + label + " STOP was re-ACKed");
        }
        catch (InvalidOperationException ex) when (ex.Message == "P03_RETRY_ACTIVE_STOP_PENDING_HOLD")
        {
            Assert(true, label + " STOP correctly blocks retry ACK");
        }
        var after = (await d04Queue.ReadAsync()).ToArray();
        Assert(before.SequenceEqual(after.Select(j => j.Id)) &&
            after.Single(j => j.Id == retry.Id).State == ModelJobState.Cancelling,
            label + " queue/history unchanged");
    }
    var d04PullReviewed = ModelCatalog.Get("tinyllama") with
    {
        EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
        ExactTag = "tinyllama:d04-stop-retry", Version = "synthetic-fixture",
        License = "synthetic-license", ArtifactBytes = 100,
        RequiredDiskBytes = 200, RecommendedRamBytes = 300,
        ExpectedSha256 = new string('b', 64),
        ExpectedManifestDigestSha256 = new string('a', 64),
        ImmutableRevision = "sha256:" + new string('a', 64),
        CompatibilityReviewed = true,
        LicenseEvidenceUri = new Uri("https://ollama.com/library/tinyllama"),
        CompatibilityEvidenceUri = new Uri("https://ollama.com/library/tinyllama"),
        ReviewedRightsReceiptId = "rights-d04-stop-fixture"
    };
    var d04PullFailed = await d04Queue.EnqueueVerifiedPullAsync(d04PullReviewed, true);
    await d04Queue.UpdateAsync(d04PullFailed.Id,
        j => j with { State = ModelJobState.Failed, Status = "Synthetic failure" });
    await AssertStopPendingRetryAsync(d04PullFailed, "D04 Pull");

    var ggufPath = Path.Combine(d04RetryRoot, "d04-stop-fixture.gguf");
    var ggufBytes = Encoding.ASCII.GetBytes("GGUF-retry-STOP-fixture");
    await File.WriteAllBytesAsync(ggufPath, ggufBytes);
    var ggufSha = Convert.ToHexString(
        System.Security.Cryptography.SHA256.HashData(ggufBytes)).ToLowerInvariant();
    var ggufFailed = await d04Queue.EnqueueVerifiedGgufAsync(
        "tinyllama:d04-stop-gguf", ggufPath, ggufBytes.LongLength,
        ggufSha, "gguf-rights-d04-stop-fixture",
        "https://ollama.com/library/tinyllama");
    await d04Queue.UpdateAsync(ggufFailed.Id,
        j => j with { State = ModelJobState.Failed, Status = "Synthetic failure" });
    await AssertStopPendingRetryAsync(ggufFailed, "D04 GGUF");
}
finally { Directory.Delete(d04RetryRoot, recursive: true); }

// B04: an old backup may contain stale RUNNING/CANCELLING states. Explicit
// rollback consent does not transfer a current execution lease or STOP owner.
var b04RestoreRoot = Path.Combine(Path.GetTempPath(),
    "NOX_P03_BACKUP_ACTIVE_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(b04RestoreRoot);
try
{
    var b04Store = new ModelDownloadQueueStore(b04RestoreRoot);
    var b04Path = Path.Combine(b04RestoreRoot, "p03-model-download-queue.json");
    var b04Backup = b04Path + ".bak";
    var b04When = DateTimeOffset.UtcNow;
    var b04OwnerJob = new ModelJob(Guid.NewGuid(), ModelJobKind.OllamaPull,
        "tinyllama:b04-rollback", null, true, "https://ollama.com/library/tinyllama",
        b04When, b04When, ModelJobState.Queued,
        ExpectedOllamaDigest: new string('a',64),
        ImmutableRevision: "sha256:" + new string('a',64), RightsReceiptId: "b04-owner");
    var b04Json = new JsonSerializerOptions(JsonSerializerDefaults.Web);
    var b04Original = JsonSerializer.Serialize(new[] { b04OwnerJob }, b04Json);
    await File.WriteAllTextAsync(b04Path, b04Original);
    async Task B04RejectStaleBackupAsync(ModelJobState state)
    {
        var stale = b04OwnerJob with { Id = Guid.NewGuid(), State = state };
        await File.WriteAllTextAsync(b04Backup,
            JsonSerializer.Serialize(new[] { stale }, b04Json));
        try { await b04Store.RestoreBackupAsync(true); }
        catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_BACKUP_ACTIVE_RESTORE_HOLD")
        {
            Assert(await File.ReadAllTextAsync(b04Path) == b04Original,
                "B04 stale " + state + " backup rejected; owner queue bytes unchanged");
            return;
        }
        throw new Exception("FAIL B04 stale " + state + " backup admitted");
    }
    await B04RejectStaleBackupAsync(ModelJobState.Running);
    await B04RejectStaleBackupAsync(ModelJobState.Cancelling);
    var b04Terminal = b04OwnerJob with { Id = Guid.NewGuid(), State = ModelJobState.Completed };
    await File.WriteAllTextAsync(b04Backup,
        JsonSerializer.Serialize(new[] { b04Terminal }, b04Json));
    await b04Store.RestoreBackupAsync(true);
    Assert((await b04Store.ReadAsync()).Single().Id == b04Terminal.Id,
        "B04 owner-confirmed terminal backup restores without starting work");
    Assert(Directory.GetFiles(b04RestoreRoot,
            "p03-model-download-queue.json.pre_restore.*").Length == 1,
        "B04 original queue snapshot preserved for NO-LOSS rollback");

    // R5 owner/STOP regression: a stale backup cannot rewrite terminal proof.
    var terminalBytes = await File.ReadAllBytesAsync(b04Path);
    var existingRestoreSnapshots = Directory.GetFiles(b04RestoreRoot,
        "p03-model-download-queue.json.pre_restore.*").Length;
    async Task B04RejectTerminalRollbackAsync(ModelJob[] backupJobs, string label)
    {
        await File.WriteAllTextAsync(b04Backup, JsonSerializer.Serialize(backupJobs, b04Json));
        var denied = false;
        try { await b04Store.RestoreBackupAsync(true); }
        catch (InvalidDataException ex) when (ex.Message == "P03_QUEUE_BACKUP_TERMINAL_NO_LOSS_HOLD")
        { denied = true; }
        Assert(denied &&
            (await File.ReadAllBytesAsync(b04Path)).SequenceEqual(terminalBytes) &&
            Directory.GetFiles(b04RestoreRoot,
                "p03-model-download-queue.json.pre_restore.*").Length == existingRestoreSnapshots,
            label);
    }
    await B04RejectTerminalRollbackAsync(
        new[] { b04Terminal with { State = ModelJobState.Queued } },
        "B04 R5 terminal JobID cannot be resurrected by stale backup");
    await B04RejectTerminalRollbackAsync(Array.Empty<ModelJob>(),
        "B04 R5 missing terminal JobID cannot erase STOP and install history");
    await B04RejectTerminalRollbackAsync(
        new[] { b04Terminal with { Status = "unverified replacement" } },
        "B04 R5 terminal owner record cannot be overwritten");
    await File.WriteAllTextAsync(b04Backup, JsonSerializer.Serialize(new[] { b04Terminal }, b04Json));
    await b04Store.RestoreBackupAsync(true);
    Assert((await b04Store.ReadAsync()).Single() == b04Terminal,
        "B04 R5 unchanged terminal backup remains owner-restorable");
}
finally { Directory.Delete(b04RestoreRoot, recursive: true); }

// Only the official loopback API shapes used by the original GGUF importer.
sealed class D04RightsGgufHandler(string modelTag, string localDigest) : HttpMessageHandler
{
    public bool ExistingTag { get; set; }
    public bool FailTagsLookup { get; set; }
    public bool AppearOnSecondTagsCheck { get; set; }
    public int TagsChecks { get; set; }
    public int CreateCalls { get; private set; }
    private bool _created;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        var path = request.RequestUri?.AbsolutePath;
        string body;
        if (request.Method == HttpMethod.Head &&
            path is not null && path.StartsWith("/api/blobs/sha256:", StringComparison.Ordinal))
            body = "";
        else if (request.Method == HttpMethod.Post && path == "/api/create")
        {
            CreateCalls++; _created = true;
            body = JsonSerializer.Serialize(new { status = "success" }) + Environment.NewLine;
        }
        else if (request.Method == HttpMethod.Get && path == "/api/tags")
        {
            TagsChecks++;
            if (FailTagsLookup)
                return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.ServiceUnavailable));
            bool present = ExistingTag || _created || (AppearOnSecondTagsCheck && TagsChecks > 1);
            body = present
                ? JsonSerializer.Serialize(new { models = new[] { new { name = modelTag, digest = localDigest } } })
                : "{\"models\":[]}";
        }
        else throw new InvalidOperationException("D04 fixture refuses unexpected Ollama request");
        return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK) {
            Content = new StringContent(body, Encoding.UTF8, "application/json")
        });
    }
}

sealed class SilentP03Sink : IModelLifecycleEventSink
{
    public ValueTask PublishToP01Async(ModelLifecycleEvent evt, CancellationToken ct) => ValueTask.CompletedTask;
    public ValueTask PublishToP05Async(ModelLifecycleEvent evt, CancellationToken ct) => ValueTask.CompletedTask;
}

sealed class StalledOllamaHandler : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        // No existing installed model in F18 native shared-STOP fixture.
        if (request.Method == HttpMethod.Get && request.RequestUri?.AbsolutePath == "/api/tags")
            return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK) {
                Content = new StringContent("{\"models\":[]}", Encoding.UTF8, "application/json")
            });
        if (request.RequestUri?.AbsolutePath != "/api/pull")
            throw new InvalidOperationException("Only synthetic Ollama Pull is available");
        return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK) {
            Content = new StreamContent(new StalledP03Stream())
        });
    }
}

sealed class StalledP03Stream : Stream
{
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
    public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override Task<int> ReadAsync(byte[] buffer, int offset, int count,
        CancellationToken ct) => ReadAsync(buffer.AsMemory(offset, count), ct).AsTask();
    public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
    {
        await Task.Delay(Timeout.Infinite, ct);
        return 0;
    }
    public override void Flush() => throw new NotSupportedException();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long length) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}
 
internal static class P03HardlinkFixture
{
    [System.Runtime.InteropServices.DllImport("kernel32.dll",
        EntryPoint = "CreateHardLinkW",
        CharSet = System.Runtime.InteropServices.CharSet.Unicode,
        SetLastError = true)]
    internal static extern bool CreateHardLink(string link, string existing,
        IntPtr reserved);
}

// Windows-only hardlink fixture, scoped to this disposable test directory.
internal static class P03HardlinkProbe
{
    [DllImport("kernel32.dll", EntryPoint = "CreateHardLinkW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool Create(string newPath, string existingPath, IntPtr reserved);
}
