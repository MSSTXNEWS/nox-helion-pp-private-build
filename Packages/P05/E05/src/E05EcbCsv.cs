using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace NoxHelion.E05;

// Official ECB SDMX CSV (D.USD.EUR.SP00.A). Date = published observation date,
// NOT a live tick or publication timestamp. Authorization remains host-controlled.
public static class E05EcbCsv
{
    public static QuoteData ParseEurUsd(string csv, int maxRows = 600)
    {
        if (string.IsNullOrWhiteSpace(csv) || maxRows < 2 || maxRows > 10000)
            return Unavailable();
        using var text = new StringReader(csv);
        string? header = text.ReadLine();
        if (header is null) return Unavailable();
        var columns = Fields(header);
        int timeCol = columns.FindIndex(x => x == "TIME_PERIOD");
        int rateCol = columns.FindIndex(x => x == "OBS_VALUE");
        if (timeCol < 0 || rateCol < 0) return Unavailable();
        DateTimeOffset? bestAt = null;
        decimal? bestRate = null;
        for (int i = 0; i < maxRows && text.ReadLine() is { } line; i++)
        {
            var fields = Fields(line);
            if (fields.Count <= Math.Max(timeCol, rateCol)) continue;
            if (!DateTime.TryParseExact(fields[timeCol], "yyyy-MM-dd",
                CultureInfo.InvariantCulture, DateTimeStyles.None, out var day) ||
                !decimal.TryParse(fields[rateCol], NumberStyles.AllowDecimalPoint,
                    CultureInfo.InvariantCulture, out var rate) || rate <= 0)
                continue;
            var at = new DateTimeOffset(day, TimeSpan.Zero);
            if (bestAt is null || at > bestAt)
            { bestAt = at; bestRate = rate; }
        }
        return new QuoteData("eur-usd", bestRate, "USD/EUR", "ECB EXR",
            bestAt, bestRate.HasValue && bestAt.HasValue ? "SOURCE_DATED" : "UNVERIFIED");
    }
    private static QuoteData Unavailable() =>
        new("eur-usd", null, "USD/EUR", "ECB EXR", null, "UNVERIFIED");
    private static List<string> Fields(string input)
    {
        var fields = new List<string>();
        var current = new StringBuilder();
        bool quoted = false;
        for (int i = 0; i < input.Length; i++)
        {
            char ch = input[i];
            if (ch == '"')
            {
                if (quoted && i + 1 < input.Length && input[i + 1] == '"')
                { current.Append('"'); i++; }
                else quoted = !quoted;
            }
            else if (ch == ',' && !quoted)
            { fields.Add(current.ToString().Trim()); current.Clear(); }
            else current.Append(ch);
        }
        fields.Add(current.ToString().Trim());
        return quoted ? new List<string>() : fields;
    }
}