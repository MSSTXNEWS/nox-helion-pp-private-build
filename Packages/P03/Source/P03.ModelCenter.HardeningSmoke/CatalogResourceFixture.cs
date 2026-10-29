using Nox.P03;

// Existing-source native fixture: no network, model download or fake review authority.
// ownerReceiptVerified=true below is a synthetic test input, not production evidence.
internal static class CatalogResourceFixture
{
    public static void Run()
    {
        var seed = ModelCatalog.Get("phi4") with {
            EvidenceStatus=CatalogEvidenceStatus.ArtifactVerified,
            ExactTag="phi4:mini", Version="fixture", License="fixture-license",
            ArtifactBytes=100, RequiredDiskBytes=100, RecommendedRamBytes=200,
            RecommendedVramBytes=null, ExpectedSha256=new string('a',64),
            ExpectedManifestDigestSha256=new string('b',64),
            LicenseEvidenceUri=new Uri("https://example.org/license"),
            CompatibilityEvidenceUri=new Uri("https://example.org/compatibility"),
            ImmutableRevision=new string('c',64), CompatibilityReviewed=true
        };
        var cases = new (long? disk, long? ram, long? vram, bool allowed)[] {
            (100,200,null,true), (101,null,200,true), (100,200,200,true),
            (99,200,null,false), (null,200,null,false), (0,200,null,false),
            (-1,200,null,false), (100,null,null,false), (100,0,200,false),
            (100,-1,200,false), (100,200,0,false), (100,200,-1,false)
        };
        foreach (var (disk,ram,vram,allowed) in cases)
        {
            var entry = seed with { RequiredDiskBytes=disk,
                RecommendedRamBytes=ram, RecommendedVramBytes=vram };
            if (entry.CanOfferOneClickPull != allowed)
                throw new Exception($"Catalogue resource policy mismatch: {disk}/{ram}/{vram}");
            var candidate = new ModelArtifactReviewCandidate("phi4", "https://ollama.com/library/phi4",
                entry.ExactTag, entry.Version, entry.License, entry.LicenseEvidenceUri!.AbsoluteUri,
                entry.ArtifactBytes, disk, ram, vram, entry.ExpectedSha256,
                entry.ExpectedManifestDigestSha256, entry.CompatibilityEvidenceUri!.AbsoluteUri,
                entry.ImmutableRevision, true, "synthetic-fixture-receipt", "OWNER_VERIFIED");
            var promoted = ModelArtifactReviewRegistry.TryPromote(candidate, true, out var result);
            if (promoted != allowed || (!allowed && result is not null))
                throw new Exception($"Review promotion resource policy mismatch: {disk}/{ram}/{vram}");
        }
        if (ModelArtifactReviewRegistry.TryPromote(null, true, out var absent) || absent is not null)
            throw new Exception("Absent candidate must remain unpromoted");
        Console.WriteLine("R29_CATALOG_RESOURCES_PASS 12 cases x catalogue/promotion + absent candidate");
    }
}
