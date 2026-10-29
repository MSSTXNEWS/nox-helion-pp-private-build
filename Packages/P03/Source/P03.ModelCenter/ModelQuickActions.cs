using System.Collections.Immutable;
namespace Nox.P03;

/// <summary>
/// Discovery and quick-selection ONLY. The single existing P03 queue/worker and
/// Ollama adapter perform approved installs. This catalog never issues HTTP calls.
/// In particular, an external model repository URL is not an artifact URL or license.
/// </summary>
public sealed record ModelQuickSlot(string Id, string DisplayName, string Role);
public sealed record ExternalWeightLead(string Id, string DisplayName, string Role, Uri ProjectPage,
    string Status = "REVIEW_REQUIRED", bool DownloadAllowed = false);

public static class ModelQuickActions
{
    public static ImmutableArray<ModelQuickSlot> OllamaSlots { get; } =
    [
        new("qwen3", "Qwen 3", "CHAT"),
        new("qwen3-coder", "Qwen 3 Coder", "CODE"),
        new("qwen2.5", "Qwen 2.5", "CHAT"),
        new("qwen2.5-coder", "Qwen 2.5 Coder", "CODE"),
        new("llama3.1", "Llama 3.1", "CHAT"),
        new("llama3.2", "Llama 3.2", "CHAT"),
        new("deepseek-r1", "DeepSeek R1", "REASON"),
        new("gemma3", "Gemma 3", "VISION"),
        new("mistral", "Mistral", "CHAT"),
        new("phi4", "Phi 4", "REASON"),
        new("tinyllama", "TinyLlama", "CHAT"),
        new("gpt-oss", "GPT-OSS", "REASON"),
        new("qwen3-vl", "Qwen 3 VL", "VISION"),
        new("llava", "LLaVA", "VISION"),
        new("gemma2", "Gemma 2", "CHAT"),
        new("mxbai-embed-large", "Mixedbread Embed", "EMBEDDING"),
        new("devstral", "Devstral", "CODE"),
        new("granite3.1-dense", "Granite", "CHAT"),
        new("mistral-nemo", "Mistral Nemo", "CHAT"),
        new("phi3", "Phi 3", "CHAT"),
    ];

    public static ImmutableArray<ExternalWeightLead> ExternalLeads { get; } =
    [
        new("asr-whisper-small", "Whisper small", "ASR", new Uri("https://huggingface.co/openai/whisper-small")),
        new("asr-whisper-large-v3", "Whisper large-v3", "ASR", new Uri("https://huggingface.co/openai/whisper-large-v3")),
        new("asr-faster-whisper", "faster-whisper", "ASR", new Uri("https://github.com/SYSTRAN/faster-whisper")),
        new("tts-piper-voices", "Piper Voices", "TTS", new Uri("https://huggingface.co/rhasspy/piper-voices")),
        new("tts-xtts-v2", "XTTS-v2", "TTS", new Uri("https://huggingface.co/coqui/XTTS-v2")),
        new("tts-mms-rus", "MMS TTS Russian", "TTS", new Uri("https://huggingface.co/facebook/mms-tts-rus")),
        new("tts-mms-spa", "MMS TTS Spanish", "TTS", new Uri("https://huggingface.co/facebook/mms-tts-spa")),
        new("tts-kokoro", "Kokoro", "TTS", new Uri("https://huggingface.co/hexgrad/Kokoro-82M")),
        new("image-sdxl", "Stable Diffusion XL", "IMAGE", new Uri("https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0")),
        new("image-flux-schnell", "FLUX.1 schnell", "IMAGE", new Uri("https://huggingface.co/black-forest-labs/FLUX.1-schnell")),
        new("image-qwen", "Qwen Image", "IMAGE", new Uri("https://huggingface.co/Qwen/Qwen-Image")),
        new("video-wan", "Wan 2.1 T2V 1.3B", "VIDEO", new Uri("https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B")),
        new("video-ltx", "LTX Video", "VIDEO", new Uri("https://huggingface.co/Lightricks/LTX-Video")),
        new("video-cogvideo", "CogVideoX 2B", "VIDEO", new Uri("https://huggingface.co/THUDM/CogVideoX-2b")),
        new("video-hunyuan", "Hunyuan Video", "VIDEO", new Uri("https://huggingface.co/tencent/HunyuanVideo")),
        new("train-qwen3-0.6b", "Qwen3 0.6B / LoRA candidate", "TRAINING", new Uri("https://huggingface.co/Qwen/Qwen3-0.6B")),
        new("aligner-wav2vec", "Wav2Vec2 aligner candidate", "ALIGNER", new Uri("https://huggingface.co/facebook/wav2vec2-base-960h")),
    ];

    /// <summary>A genuine quick button can request ONLY a host-attested catalog
    /// model through EnqueueVerifiedPullAsync. Explicit license ack is required.</summary>
    // A button for one family must never silently install a different
    // family's artifact, even if a direct catalog entry claims to be reviewed.
    private static bool MatchesFamily(ModelCatalogEntry model) =>
        !string.IsNullOrWhiteSpace(model.ExactTag) &&
        model.ExactTag.StartsWith(model.Id + ":", StringComparison.OrdinalIgnoreCase);

    public static bool TryResolveApprovedOllamaPull(
        string? selectedId, IReadOnlyCollection<ModelCatalogEntry> approvedCatalog,
        bool licenseAcknowledged, bool hostPullCapability, out ModelCatalogEntry? model)
    {
        model = null;
        if (!licenseAcknowledged || !hostPullCapability || approvedCatalog is null ||
            string.IsNullOrWhiteSpace(selectedId) ||
            !OllamaSlots.Any(x => string.Equals(x.Id, selectedId, StringComparison.Ordinal)))
            return false;
        var matches = approvedCatalog.Where(x => x.Id == selectedId).Take(2).ToArray();
        if (matches.Length != 1 || !matches[0].CanOfferOneClickPull || !MatchesFamily(matches[0])) return false;
        model = matches[0];
        return true;
    }

    /// <summary>Exact tags are discovery leads, not immutable pins. The existing
    /// queue is used only after independent artifact and host approval.</summary>
    public static bool TryResolveApprovedOllamaPullExactTag(
        string? exactTag, IReadOnlyCollection<ModelCatalogEntry> approvedCatalog,
        bool licenseAcknowledged, bool hostPullCapability, out ModelCatalogEntry? model)
    {
        model = null;
        if (!licenseAcknowledged || !hostPullCapability || approvedCatalog is null ||
            string.IsNullOrWhiteSpace(exactTag)) return false;
        var lead = ModelTagReviewLeads.ExactTags.FirstOrDefault(x =>
            string.Equals(x.ExactTag, exactTag, StringComparison.Ordinal));
        if (lead is null) return false;
        var matches = approvedCatalog.Where(x =>
            string.Equals(x.ExactTag, exactTag, StringComparison.Ordinal) &&
            string.Equals(x.Id, lead.FamilyId, StringComparison.Ordinal)).Take(2).ToArray();
        if (matches.Length != 1 || !matches[0].CanOfferOneClickPull || !MatchesFamily(matches[0])) return false;
        model = matches[0];
        return true;
    }

    public static bool VerifyDiscoveryIntegrity() =>
        OllamaSlots.Length >= 20 &&
        OllamaSlots.Select(x=>x.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() == OllamaSlots.Length &&
        OllamaSlots.All(x => ModelCatalog.OfficialFamilies.Any(m => m.Id == x.Id)) &&
        ExternalLeads.Length >= 12 &&
        ExternalLeads.Select(x=>x.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() == ExternalLeads.Length &&
        ExternalLeads.All(x => x.Status == "REVIEW_REQUIRED" && !x.DownloadAllowed &&
            x.ProjectPage.Scheme == Uri.UriSchemeHttps &&
            string.IsNullOrEmpty(x.ProjectPage.UserInfo)) &&
        new [] { "ASR", "TTS", "IMAGE", "VIDEO", "TRAINING" }
            .All(role=>ExternalLeads.Any(x=>x.Role==role));
}
