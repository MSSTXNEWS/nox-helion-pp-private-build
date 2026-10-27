using System;

namespace Nox.P05.Reporting
{
    public enum EvidenceStatus
    {
        Unknown = 0,
        NotRun = 1,
        Present = 2,
        Passed = 3,
        Failed = 4
    }

    public enum DriveSyncStatus
    {
        Unknown = 0,
        Pending = 1,
        Synced = 2,
        ReadBackVerified = 3,
        Failed = 4
    }

    /// <summary>
    /// A truthful, source-neutral snapshot of one installer/application run.
    /// Null metric values mean "not measured"; zero is reserved for a real measured zero.
    /// This type performs no I/O and does not imply that a build, runtime, or acceptance ran.
    /// </summary>
    public sealed class InstallerRunReport
    {
        public string TaskId { get; }
        public string RunId { get; }
        public string WorkerId { get; }
        public string SourceCommit { get; }
        public string SourceTree { get; }
        public string ExecutableSha256 { get; }
        public DateTimeOffset? StartedAtUtc { get; }
        public DateTimeOffset? FinishedAtUtc { get; }
        public EvidenceStatus SourceStatus { get; }
        public EvidenceStatus IntegratedStatus { get; }
        public EvidenceStatus WindowsVerificationStatus { get; }
        public EvidenceStatus ReleaseAcceptanceStatus { get; }
        public DriveSyncStatus DriveSyncStatus { get; }
        public string DriveReceiptId { get; }
        public double? ModelLoadSeconds { get; }
        public double? TrainingStepsPerSecond { get; }
        public double? TrainingLoss { get; }
        public string MetricsNotMeasuredReason { get; }

        public double? ElapsedSeconds
        {
            get
            {
                if (!StartedAtUtc.HasValue || !FinishedAtUtc.HasValue)
                    return null;
                return (FinishedAtUtc.Value - StartedAtUtc.Value).TotalSeconds;
            }
        }

        public InstallerRunReport(
            string taskId,
            string runId,
            string workerId,
            string sourceCommit,
            string sourceTree,
            string executableSha256,
            DateTimeOffset? startedAtUtc,
            DateTimeOffset? finishedAtUtc,
            EvidenceStatus sourceStatus,
            EvidenceStatus integratedStatus,
            EvidenceStatus windowsVerificationStatus,
            EvidenceStatus releaseAcceptanceStatus,
            DriveSyncStatus driveSyncStatus,
            string driveReceiptId,
            double? modelLoadSeconds,
            double? trainingStepsPerSecond,
            double? trainingLoss,
            string metricsNotMeasuredReason)
        {
            TaskId = Required(taskId, nameof(taskId));
            RunId = Required(runId, nameof(runId));
            WorkerId = Required(workerId, nameof(workerId));
            SourceCommit = Optional(sourceCommit);
            SourceTree = Optional(sourceTree);
            ExecutableSha256 = Optional(executableSha256);
            StartedAtUtc = AsUtc(startedAtUtc, nameof(startedAtUtc));
            FinishedAtUtc = AsUtc(finishedAtUtc, nameof(finishedAtUtc));
            if (StartedAtUtc.HasValue && FinishedAtUtc.HasValue && FinishedAtUtc.Value < StartedAtUtc.Value)
                throw new ArgumentException("FinishedAtUtc must not precede StartedAtUtc.", nameof(finishedAtUtc));

            SourceStatus = sourceStatus;
            IntegratedStatus = integratedStatus;
            WindowsVerificationStatus = windowsVerificationStatus;
            ReleaseAcceptanceStatus = releaseAcceptanceStatus;
            DriveSyncStatus = driveSyncStatus;
            DriveReceiptId = Optional(driveReceiptId);
            ModelLoadSeconds = NonNegative(modelLoadSeconds, nameof(modelLoadSeconds));
            TrainingStepsPerSecond = NonNegative(trainingStepsPerSecond, nameof(trainingStepsPerSecond));
            TrainingLoss = NonNegative(trainingLoss, nameof(trainingLoss));
            MetricsNotMeasuredReason = Optional(metricsNotMeasuredReason);

            if (DriveSyncStatus == DriveSyncStatus.ReadBackVerified && String.IsNullOrWhiteSpace(DriveReceiptId))
                throw new ArgumentException("A read-back verified Drive status requires a receipt ID.", nameof(driveReceiptId));
            if ((ModelLoadSeconds.HasValue || TrainingStepsPerSecond.HasValue || TrainingLoss.HasValue) &&
                StartedAtUtc.HasValue && !FinishedAtUtc.HasValue)
                throw new ArgumentException("Measured run metrics require a completed run timestamp.", nameof(finishedAtUtc));
        }

        private static string Required(string value, string name)
        {
            if (String.IsNullOrWhiteSpace(value))
                throw new ArgumentException("A non-empty value is required.", name);
            return value.Trim();
        }

        private static string Optional(string value)
        {
            return String.IsNullOrWhiteSpace(value) ? null : value.Trim();
        }

        private static DateTimeOffset? AsUtc(DateTimeOffset? value, string name)
        {
            if (!value.HasValue)
                return null;
            return value.Value.ToUniversalTime();
        }

        private static double? NonNegative(double? value, string name)
        {
            if (value.HasValue && (Double.IsNaN(value.Value) || Double.IsInfinity(value.Value) || value.Value < 0))
                throw new ArgumentOutOfRangeException(name, "Metric must be finite and non-negative.");
            return value;
        }
    }
}
ccdcd861a6f96942219a9af5f8e092319b4e4cd6499e2f06a0d52316caaf724e  -