// NOX HELION MICRO LAUNCHER · N8 G5B isolated SOURCE candidate, not release.
// Build with Windows .NET Framework 4.8 C# compiler, NO extra SDK:
// "%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe
// /platform:x64 /optimize+ /reference:System.Net.Http.dll
// /reference:System.Windows.Forms.dll /reference:System.Drawing.dll NOX.MicroLauncher.cs
// RELEASE GATE: I0 alone inserts immutable official Setup URL / BuildID / SHA256.
// Blank configuration means NO download / NO installation; DO NOT ship to user.
// This is not a second installer: verified downloaded Setup is the ONLY installer.
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace NoxHelion.MicroLauncher {
internal static class Program {
    // I0 canonical release owner: fill only after ONE official Setup is published.
    private const string OfficialSetupUrl = "";
    private const string OfficialSetupSha256 = "";
    private const string OfficialBuildId = "";
    private const long MaxSetupBytes = 1024L * 1024L * 1024L;

    private static bool Https(Uri uri) {
        return uri != null && uri.IsAbsoluteUri &&
            uri.Scheme.Equals("https", StringComparison.OrdinalIgnoreCase) &&
            !uri.IsLoopback && String.IsNullOrEmpty(uri.UserInfo);
    }
    private static bool Ready(out Uri source) {
        source = null;
        if (String.IsNullOrWhiteSpace(OfficialSetupUrl) ||
            !Regex.IsMatch(OfficialSetupSha256, @"\A[0-9a-fA-F]{64}\z") ||
            OfficialSetupSha256 == new String('0', 64) ||
            !Regex.IsMatch(OfficialBuildId, @"\A[A-Za-z0-9._-]{1,80}\z") ||
            !Uri.TryCreate(OfficialSetupUrl, UriKind.Absolute, out source) ||
            !Https(source)) return false;
        var host = source.Host;
        var resource = source.AbsolutePath;
        if (host.Equals("github.com", StringComparison.OrdinalIgnoreCase))
            return resource.StartsWith("/MSSTXNEWS/nox-helion-pp-private-build/releases/download/",
                                       StringComparison.OrdinalIgnoreCase);
        if (host.Equals("gitlab.com", StringComparison.OrdinalIgnoreCase))
            return resource.StartsWith("/s-grouptwet/nox-helion-pp-private-build/",
                                       StringComparison.OrdinalIgnoreCase);
        if (host.Equals("drive.google.com", StringComparison.OrdinalIgnoreCase))
            return resource.StartsWith("/uc", StringComparison.OrdinalIgnoreCase) ||
                   resource.StartsWith("/file/d/", StringComparison.OrdinalIgnoreCase);
        return false;
    }
    private static bool Redirect(HttpStatusCode status) {
        int n = (int)status;
        return n == 301 || n == 302 || n == 303 || n == 307 || n == 308;
    }

    // HTTPS redirects are explicit and fail closed; Setup SHA is pinned in this EXE,
    // NEVER downloaded from the same mutable link.
    private static async Task<string> FetchAndHash(
        Uri from, string temporary, CancellationToken cancel, Action<long,long?> update) {
        using (var handler = new HttpClientHandler {
            AllowAutoRedirect = false, UseCookies = false,
            AutomaticDecompression = DecompressionMethods.None
        })
        using (var client = new HttpClient(handler)) {
            client.Timeout = TimeSpan.FromMinutes(20);
            Uri target = from;
            for (int hop = 0; hop < 6; ++hop) {
                if (!Https(target)) throw new InvalidDataException("HTTPS_ONLY_HOLD");
                using (var response = await client.GetAsync(
                    target, HttpCompletionOption.ResponseHeadersRead, cancel)) {
                    if (Redirect(response.StatusCode)) {
                        if (hop == 5 || response.Headers.Location == null)
                            throw new InvalidDataException("REDIRECT_LIMIT_HOLD");
                        Uri destination = response.Headers.Location.IsAbsoluteUri
                            ? response.Headers.Location
                            : new Uri(target, response.Headers.Location);
                        if (!Https(destination))
                            throw new InvalidDataException("REDIRECT_HTTPS_HOLD");
                        target = destination;
                        continue;
                    }
                    if (!response.IsSuccessStatusCode)
                        throw new HttpRequestException("SETUP_DOWNLOAD_HOLD");
                    long? length = response.Content.Headers.ContentLength;
                    if (length.HasValue && (length.Value < 4096 || length.Value > MaxSetupBytes))
                        throw new InvalidDataException("SETUP_LENGTH_HOLD");
                    using (var input = await response.Content.ReadAsStreamAsync())
                    using (var output = new FileStream(temporary, FileMode.CreateNew,
                        FileAccess.Write, FileShare.None, 65536, true))
                    using (var sha = SHA256.Create()) {
                        long count = 0;
                        var buffer = new byte[65536];
                        int n;
                        while ((n = await input.ReadAsync(buffer, 0, buffer.Length, cancel)) > 0) {
                            count += n;
                            if (count > MaxSetupBytes)
                                throw new InvalidDataException("SETUP_SIZE_HOLD");
                            await output.WriteAsync(buffer, 0, n, cancel);
                            sha.TransformBlock(buffer, 0, n, buffer, 0);
                            if (update != null) update(count, length);
                        }
                        await output.FlushAsync(cancel);
                        sha.TransformFinalBlock(new byte[0], 0, 0);
                        if (count < 4096 || (length.HasValue && count != length.Value))
                            throw new InvalidDataException("SETUP_TRUNCATED_HOLD");
                        return BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
                    }
                }
            }
            throw new InvalidDataException("REDIRECT_LIMIT_HOLD");
        }
    }
    private static bool IsPeExe(string filename) {
        using (var f = new FileStream(filename, FileMode.Open, FileAccess.Read, FileShare.Read))
            return f.ReadByte() == 0x4d && f.ReadByte() == 0x5a;
    }
    [STAThread]
    private static void Main() {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new MicroWindow());
    }
    private sealed class MicroWindow : Form {
        private readonly Label state;
        private readonly ProgressBar bar;
        private readonly Button stop;
        private readonly CancellationTokenSource cancel = new CancellationTokenSource();
        private bool downloading;
        private string temporary;
        internal MicroWindow() {
            Text = "NOX HELION - official Setup";
            Width = 500; Height = 170;
            MaximizeBox = false; MinimizeBox = false;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            state = new Label {Left=16, Top=17, Width=452, Height=38, Text="Validating approved release..."};
            bar = new ProgressBar {Left=16, Top=61, Width=452, Height=19,
                Style=ProgressBarStyle.Marquee};
            stop = new Button {Left=370, Top=90, Width=98, Height=27, Text="Cancel"};
            Controls.Add(state); Controls.Add(bar); Controls.Add(stop);
            stop.Click += (s,e) => { if (downloading) {
                stop.Enabled = false; cancel.Cancel();
            } else Close(); };
            Shown += async (s,e) => await Execute();
        }
        private void Hold(string message) {
            state.Text = message; bar.Style=ProgressBarStyle.Continuous; bar.Value=0;
            stop.Text="Close"; stop.Enabled=true;
        }
        private async Task Execute() {
            Uri approved;
            if (!Ready(out approved)) {
                Hold("CONFIG_HOLD: I0 must pin one official URL / SHA256 / BuildID.");
                return; // no network, file, or execution without approved immutable pins
            }
            downloading = true;
            temporary = Path.Combine(Path.GetTempPath(),
                "NOX-HELION-Setup-" + Guid.NewGuid().ToString("N") + ".exe");
            try {
                state.Text = "Downloading official Setup over verified HTTPS...";
                string observed = await FetchAndHash(approved, temporary, cancel.Token,
                    (received, total) => { if (total.HasValue && total.Value>0) {
                        bar.Style = ProgressBarStyle.Continuous;
                        bar.Value = Math.Min(100,(int)(received*100/total.Value));
                    }});
                downloading=false;
                if (!String.Equals(observed, OfficialSetupSha256,
                                   StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("SHA256_MISMATCH_HOLD");
                if (!IsPeExe(temporary)) throw new InvalidDataException("NOT_PE_EXE_HOLD");
                state.Text = "Exact SHA256 PASS. Launching ONE official Setup...";
                bar.Style=ProgressBarStyle.Continuous; bar.Value=100;
                stop.Enabled=false; // installer owns its own cancellation / elevation
                using (var installer = Process.Start(new ProcessStartInfo {
                    FileName=temporary, WorkingDirectory=Path.GetDirectoryName(temporary),
                    UseShellExecute=true, Verb="open"
                })) {
                    if (installer==null) throw new IOException("LAUNCH_HOLD");
                    // Exiting Setup process is NOT proof installation passed.
                    await Task.Run(() => installer.WaitForExit());
                }
                state.Text = "Setup exited; I0/E07 must verify real installation.";
                stop.Text="Close"; stop.Enabled=true;
            } catch (OperationCanceledException) {
                downloading=false; Hold("CANCELLED - no unverified Setup was launched.");
            } catch (Exception ex) {
                downloading=false; Hold("HOLD: " + ex.GetType().Name +
                    ". No unverified Setup was launched.");
            } finally {
                // No ZIP; dispose incomplete or verified downloaded EXE.
                if (!String.IsNullOrEmpty(temporary)) {
                    try { File.Delete(temporary); }
                    catch (IOException) {} catch (UnauthorizedAccessException) {}
                }
            }
        }
        protected override void OnFormClosing(FormClosingEventArgs e) {
            if (downloading) { e.Cancel=true; cancel.Cancel(); return; }
            base.OnFormClosing(e);
        }
    }
}
}
