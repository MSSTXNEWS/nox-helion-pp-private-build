// E06 owner-only additive WPF -> original Python read-only diagnostic.
// This creates no secondary UI/LLM/HTTP server/SQLite and accepts no page-supplied argv.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NoxP01;
public partial class MainWindow
{
    private const string PinnedPythonExeSha256 = "4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3";

    private async Task ReportOriginalPythonDiagnosticAsync(string? requestId, string routeId)
    {
        var original = Path.Combine(AppContext.BaseDirectory, "Backend", "NOX_HELION_PRIVATE_CANDIDATE.exe");
        try
        {
            // The owner-approved original backend is read-only queried; no arbitrary path/argument/command.
            if (!File.Exists(original) || (File.GetAttributes(original) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Original Python backend missing or unsafe");
            await using (var input = File.OpenRead(original))
            {
                var digest = Convert.ToHexString(await SHA256.HashDataAsync(input)).ToLowerInvariant();
                if (!string.Equals(digest, PinnedPythonExeSha256, StringComparison.Ordinal))
                    throw new IOException("Original Python backend SHA256 mismatch");
            }
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo
            {
                FileName = original,
                Arguments = "--diagnose",
                WorkingDirectory = AppContext.BaseDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            if (!process.Start()) throw new IOException("Original Python process could not start");
            using var limit = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            try
            {
                var outputTask = process.StandardOutput.ReadToEndAsync(limit.Token);
                var errorTask = process.StandardError.ReadToEndAsync(limit.Token);
                await process.WaitForExitAsync(limit.Token);
                var output = await outputTask;
                var error = await errorTask;
                if (process.ExitCode != 0 || output.Length > 65536 || error.Length > 8192)
                    throw new IOException("Original Python diagnostic did not finish safely");
                using var json = JsonDocument.Parse(output);
                var root = json.RootElement;
                if (root.ValueKind != JsonValueKind.Object ||
                    !root.TryGetProperty("routes_total", out var count) ||
                    !count.TryGetInt32(out var routes) ||
                    !root.TryGetProperty("cores", out var cores) ||
                    cores.ValueKind != JsonValueKind.Array)
                    throw new IOException("Original Python diagnostic contract mismatch");
                PostMessage(new
                {
                    kind = "packResult",
                    requestId,
                    routeId,
                    state = "COMPLETED",
                    diagnosticOnly = true,
                    pythonBackendSha256 = PinnedPythonExeSha256,
                    originalRoutes = routes,
                    coreCount = cores.GetArrayLength(),
                    backendAccepted = false,
                    note = "Исходное Python-ядро ответило на --diagnose. Это не проверка локальной модели или GPU."
                });
            }
            catch (OperationCanceledException)
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
                throw new IOException("Original Python diagnostic timeout");
            }
            finally
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
            }
        }
        catch (Exception exc)
        {
            WriteLog("E06_ORIGINAL_BACKEND_HOLD " + exc.GetType().Name);
            PostMessage(new {
                kind = "packResult", requestId, routeId, state = "HOLD", diagnosticOnly = true,
                backendAccepted = false,
                note = "Исходное Python-ядро недоступно либо не прошло SourceLock/SHA/протокол."
            });
        }
    }
}
