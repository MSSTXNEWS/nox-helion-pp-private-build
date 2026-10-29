// P04 actual process-control contract regression. NO model, dataset or CUDA required.
// A child process intentionally exits after ACK; none of the events may claim
// training PAUSED, RUNNING or STOPPED without a validated worker receipt.
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Reflection;
using NoxP04.GpuGuardian;

internal static class Program
{
    private sealed class ChildControl(string marker) : IGpuWorkerControl
    {
        public Task<bool> PauseAsync(CancellationToken token) => Task.FromResult(true);
        public Task<bool> ResumeAsync(CancellationToken token) => Task.FromResult(true);
        public Task<bool> RequestStopAsync(CancellationToken token)
        {
            File.WriteAllText(marker, "stop\n");
            return Task.FromResult(true);
        }
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    public static async Task<int> Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--child")
        {
            for (var i = 0; i < 300; i++)
            {
                if (File.Exists(args[1])) return 0;
                await Task.Delay(25);
            }
            return 27;
        }
        if (!OperatingSystem.IsWindows())
        {
            Console.WriteLine("HOLD: native process-contract test requires Windows.");
            return 3;
        }

        var root = Path.Combine(Path.GetTempPath(), "nox-p04-worker-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var marker = Path.Combine(root, "stop.marker");
        var seen = new ConcurrentQueue<GpuGuardianEvent>();
        try
        {
            var monitor = new NoxP04.GpuGuardian.GpuGuardian("NOX-P04-RECEIPT-TEST");
            monitor.EventRaised += seen.Enqueue;
            var host = Environment.ProcessPath ?? throw new InvalidOperationException("NO_PROCESS_PATH");
            var start = new ProcessStartInfo(host)
            {
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            if (Path.GetFileNameWithoutExtension(host).Equals("dotnet", StringComparison.OrdinalIgnoreCase))
                start.ArgumentList.Add(Assembly.GetExecutingAssembly().Location);
            start.ArgumentList.Add("--child");
            start.ArgumentList.Add(marker);

            await using var child = GpuWorkerLauncher.Start(monitor, "P04-test-worker", start, new ChildControl(marker));
            Require(seen.Any(e => e.State == "HOLD" && e.Message.Contains("launched")), "LAUNCH_MUST_NOT_CLAIM_GPU_TRAINING");
            Require(await child.PauseAsync(), "PAUSE_REQUEST_NOT_ACKNOWLEDGED");
            Require(await child.ResumeAsync(), "RESUME_REQUEST_NOT_ACKNOWLEDGED");
            Require(!seen.Any(e => e.State is "PAUSED" or "RUNNING" or "STOPPED"), "ACK_MUST_NOT_CLAIM_CONFIRMED_TRAINING");
            Require(await child.StopAsync(TimeSpan.FromSeconds(10)), "CHILD_PROCESS_DID_NOT_EXIT");
            Require(seen.Any(e => e.State == "HOLD" && e.Message.Contains("verified STOPPED receipt")), "EXIT_MUST_REQUIRE_STOP_RECEIPT");
            Require(!seen.Any(e => e.State is "PAUSED" or "RUNNING" or "STOPPED"), "STOP_EXIT_MUST_NOT_FAKE_TRAINING_STATE");
            Require(!await child.StopAsync(), "EXISTING_EXIT_MUST_NOT_CLAIM_NEW_STOP");
            await child.DisposeAsync();
            await child.DisposeAsync(); // idempotent
            try
            {
                await child.PauseAsync();
                throw new InvalidOperationException("DISPOSED_CONTROL_SHOULD_THROW");
            }
            catch (ObjectDisposedException) { }
            Console.WriteLine("PASS: native process exit/ACK cannot impersonate QLoRA receipt; disposal idempotent.");
            return 0;
        }
        finally
        {
            try { Directory.Delete(root, recursive: true); } catch (IOException) { }
        }
    }
}
