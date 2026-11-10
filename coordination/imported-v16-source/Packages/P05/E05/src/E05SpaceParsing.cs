using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Xml;

namespace NoxHelion.E05;

// Parsing only; E06 must supply licensed HTTPS URLs and host-configured HttpClient.
public sealed record QuoteData(string FeedId, decimal? Value, string Unit, string Source,
    DateTimeOffset? SourceTime, string Status);
public sealed record NewsHeadline(string Title, Uri Link, string Source,
    DateTimeOffset? PublishedAt);
public sealed record WeatherData(double? TemperatureC, double? HumidityPercent,
    double? WindKmh, DateTimeOffset? SourceTime, string Status);

public static class SpaceParsers
{
    // Paths such as "rates.USD" or "bitcoin.eur" are provider configuration, not guesses.
    public static QuoteData ParseQuote(string json, string id, string path,
        string timePath, string unit, string source)
    {
        using var doc = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 24 });
        var price = Pick(doc.RootElement, path);
        var stamp = Pick(doc.RootElement, timePath);
        decimal? number = price.HasValue && price.Value.ValueKind == JsonValueKind.Number &&
            price.Value.TryGetDecimal(out var v) && v > 0 ? v : null;
        var time = TryTimestamp(stamp);
        return new QuoteData(id, number, unit, source, time,
            number.HasValue && time.HasValue ? "SOURCE_DATED" : "UNVERIFIED");
    }
    public static WeatherData ParseWeather(string json)
    {
        using var doc = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 24 });
        double? Read(string key)
        {
            var e = Pick(doc.RootElement, key);
            return e.HasValue && e.Value.ValueKind == JsonValueKind.Number &&
                   e.Value.TryGetDouble(out double v) && double.IsFinite(v) ? v : null;
        }
        var observed = TryTimestamp(Pick(doc.RootElement, "current.time")) ??
            TryOffsetTimestamp(doc.RootElement);
        var temp = Read("current.temperature_2m");
        return new WeatherData(temp, Read("current.relative_humidity_2m"),
            Read("current.wind_speed_10m"), observed,
            temp.HasValue && observed.HasValue ? "SOURCE_DATED" : "UNVERIFIED");
    }
    public static IReadOnlyList<NewsHeadline> ParseRss(string xml, string source, int maxItems = 30)
    {
        if (maxItems < 1 || maxItems > 100) throw new ArgumentOutOfRangeException(nameof(maxItems));
        var result = new List<NewsHeadline>();
        var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit,
            XmlResolver = null, MaxCharactersInDocument = 524288 };
        using var reader = XmlReader.Create(new StringReader(xml), settings);
        var doc = new XmlDocument { XmlResolver = null };
        doc.Load(reader);
        var items = doc.SelectNodes("/rss/channel/item");
        if (items is null) return result;
        foreach (XmlNode node in items)
        {
            string title = node.SelectSingleNode("title")?.InnerText?.Trim() ?? "";
            string link = node.SelectSingleNode("link")?.InnerText?.Trim() ?? "";
            string published = node.SelectSingleNode("pubDate")?.InnerText?.Trim() ?? "";
            if (title.Length == 0 || title.Length > 300 ||
                !Uri.TryCreate(link, UriKind.Absolute, out var uri) ||
                uri.Scheme != Uri.UriSchemeHttps || uri.IsLoopback ||
                uri.HostNameType != UriHostNameType.Dns ||
                uri.Host.EndsWith(".local", StringComparison.OrdinalIgnoreCase) ||
                !string.IsNullOrEmpty(uri.UserInfo)) continue;
            DateTimeOffset? time = DateTimeOffset.TryParse(published,
                CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var t) ? t : null;
            result.Add(new NewsHeadline(title, uri, source, time));
            if (result.Count == maxItems) break;
        }
        return result;
    }
    // Open-Meteo may return a timezone-less current.time plus utc_offset_seconds.
    // Use only the explicit provider offset, never the operating system's local timezone.
    private static DateTimeOffset? TryOffsetTimestamp(JsonElement root)
    {
        var stamp = Pick(root, "current.time");
        var utcOffset = Pick(root, "utc_offset_seconds");
        if (stamp is null || stamp.Value.ValueKind != JsonValueKind.String ||
            utcOffset is null || utcOffset.Value.ValueKind != JsonValueKind.Number ||
            !utcOffset.Value.TryGetInt32(out var seconds) ||
            seconds % 60 != 0 || seconds < -12 * 3600 || seconds > 14 * 3600)
            return null;
        var raw = stamp.Value.GetString();
        if (raw is null || !DateTime.TryParseExact(raw,
            new[] { "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd'T'HH:mm:ss" },
            CultureInfo.InvariantCulture, DateTimeStyles.None, out var wallTime))
            return null;
        return new DateTimeOffset(wallTime, TimeSpan.FromSeconds(seconds))
            .ToUniversalTime();
    }
    private static JsonElement? Pick(JsonElement root, string path)
    {
        if (string.IsNullOrWhiteSpace(path)) return null;
        foreach (string segment in path.Split('.'))
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty(segment, out root)) return null;
        return root;
    }
    private static DateTimeOffset? TryTimestamp(JsonElement? element)
    {
        if (!element.HasValue) return null;
        var e = element.Value;
        // Timestamp must carry timezone (Z or explicit offset); no implicit local time.
        if (e.ValueKind == JsonValueKind.String)
        {
            var s = e.GetString() ?? "";
            if (!(s.EndsWith("Z", StringComparison.OrdinalIgnoreCase) ||
                (s.Length > 10 && (s.LastIndexOf('+') > 9 || s.LastIndexOf('-') > 9))))
                return null;
            if (DateTimeOffset.TryParse(s, CultureInfo.InvariantCulture,
                DateTimeStyles.AdjustToUniversal, out var t)) return t;
        }
        else if (e.ValueKind == JsonValueKind.Number && e.TryGetInt64(out long seconds))
        {
            try { return DateTimeOffset.FromUnixTimeSeconds(seconds); }
            catch (ArgumentOutOfRangeException) { }
        }
        return null;
    }
}
